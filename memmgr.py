import kvmapi, mmap, ctypes

MAP_NORESERVE = 0x4000

def copyToRam(base, data):
  buf = (ctypes.c_ubyte*len(data)).from_address(base)
  for i, x in enumerate(data):
    buf[i] = x

class MemoryExtent:
  def __init__(self, base, len):
    self.base = base
    self.len  = len

  def __repr__(self):
    return "MemoryExtent[0x%x,0x%x)" % (self.base, self.base+self.len)

  def __len__(self):
    return self.len

  def __getitem__(self, idx):
    if isinstance(idx, slice):
      newBase = self.base
      if idx.start is not None:
        assert idx.start >= 0
        newBase += idx.start

      newLen = self.len
      newLen = min(newLen, self.len - (newBase - self.base))
      if idx.stop is not None:
        if idx.stop < 0:
          newLen -= -idx.stop
        else:
          newLen = idx.stop - (idx.start or 0)

      newLen = min(newLen, self.len - (newBase - self.base))
      newLen = max(newLen, 0)
      return MemoryExtent(newBase, newLen)
    else:
      raise NotImplementedError()

  def copyFrom(self, buf=None):
    if buf is None:
      assert self.len < 16*1024*1024
      buf = bytearray(self.len)

    rbuf = (ctypes.c_ubyte*self.len).from_address(self.base)
    for i in range(min(len(buf), self.len)):
      buf[i] = rbuf[i]

    return buf

  def copyTo(self, srcBuf):
    dstBuf = (ctypes.c_ubyte*self.len).from_address(self.base)
    for i, x in enumerate(srcBuf):
      dstBuf[i] = x

class MemorySlot:
  def __init__(self, mgr, slotNo, guestPhysAddr, userspaceAddr, len, ro):
    self._mgr           = mgr
    self.slotNo         = slotNo
    self.guestPhysAddr  = guestPhysAddr
    self.userspaceAddr  = userspaceAddr
    self.len            = len
    self.ro             = ro
    self._wasAllocated  = False
    self._destroyed     = False

  def teardown(self):
    if self._destroyed:
      return

    oldLen = self.len
    self.len = 0
    self.update()

    if self._wasAllocated:
      print('@MemMgr: UNMAP (0x%x, 0x%x)' % (self.userspaceAddr, oldLen))
      kvmapi.munmap(self.userspaceAddr, oldLen)

    del self._mgr._slots[self.slotNo]
    self._mgr._freeSlots.add(self.slotNo)
    self._destroyed = True

  def update(self):
    assert not self._destroyed

    flags = 0
    if self.ro:
      flags = kvmapi.KVM_MEM_READONLY

    try:
      self._mgr._vmm.vm.setUserMemoryRegion(kvmapi.KvmUserSpaceMemoryRegion(self.slotNo, flags, self.guestPhysAddr, self.len, self.userspaceAddr))
      print('@MemMgr: MAPPED (0x%x, 0x%x)' % (self.userspaceAddr, self.len))
    except Exception as e:
      print('Warning: failed to update memory region: %s' % e)

  def toExtent(self):
    return MemoryExtent(self.userspaceAddr, self.len)

class MemoryManager:
  def __init__(self, vmm):
    self._vmm         = vmm
    self._nextSlotNo  = 0
    self._freeSlots   = set()
    self._slots       = {}

  def mapExisting(self, guestPhysAddr, userspaceAddr, len, ro=False):
    slotNo = self._allocateSlotNo()
    slot = MemorySlot(self, slotNo, guestPhysAddr, userspaceAddr, len, ro)
    slot.update()
    self._slots[slotNo] = slot
    return slot

  def mapNew(self, guestPhysAddr, len, ro=False):
    p = kvmapi.mmap(-1, len, mmap.PROT_READ | mmap.PROT_WRITE, mmap.MAP_ANON | mmap.MAP_PRIVATE | MAP_NORESERVE, -1, 0)
    if p == 0xFFFFFFFF_FFFFFFFF:
      raise Exception("failed to map RAM")

    slot = self.mapExisting(guestPhysAddr, p, len, ro)
    slot._wasAllocated = True
    return slot

  def clear(self):
    for s in list(self._slots.values()):
      s.teardown()

    assert len(self._slots) == 0
    self._nextSlotNo = 0
    self._freeSlots = set()

  def resolveSlot(self, guestPhysAddr):
    for slot in self._slots.values():
      if guestPhysAddr >= slot.guestPhysAddr and guestPhysAddr < slot.guestPhysAddr + slot.len:
        return slot

    return None

  def resolveExtent(self, guestPhysAddr):
    slot = self.resolveSlot(guestPhysAddr)
    if slot is None:
      return None

    ex = slot.toExtent()[guestPhysAddr - slot.guestPhysAddr:]
    assert ex.base >= slot.userspaceAddr
    assert ex.base + ex.len <= slot.userspaceAddr + slot.len
    return ex

  def resolveExtents(self, guestPhysAddr, len):
    bufs = []
    while len:
      extent = self.resolveExtent(guestPhysAddr)
      if extent is None:
        return None

      L = min(len, extent.len)
      bufs.append(extent[0:L])
      len -= L
      guestPhysAddr += L

    return bufs

  def read(self, guestPhysAddr, bufLen):
    extents = self.resolveExtents(guestPhysAddr, bufLen)
    if extents is None:
      return None

    b = b''
    while len(b) < bufLen:
      b += MultiReadBuffer(extents).read(bufLen - len(b))

    return b

  def write(self, guestPhysAddr, buf):
    extents = self.resolveExtents(guestPhysAddr, len(buf))
    if extents is None:
      return None

    return MultiWriteBuffer(extents).write(buf)

  def _allocateSlotNo(self):
    if len(self._freeSlots):
      return self._freeSlots.pop()
    slotNo = self._nextSlotNo
    self._nextSlotNo += 1
    return slotNo

class MultiReadBuffer:
  # (bufs: [MemoryExtent...])
  def __init__(self, extents):
    self._extents = extents

  @property
  def remaining(self):
    L = 0
    for extent in self._extents:
      L += extent.len
    return L

  def read(self, n):
    if len(self._extents) == 0:
      return b''

    extent = self._extents[0]
    n = min(n, extent.len)
    b = bytes(extent[:n].copyFrom())
    if extent.len - n == 0:
      self._extents = self._extents[1:]
    else:
      self._extents[0] = self._extents[0][n:]

    return b

class MultiWriteBuffer:
  # (bufs: [MemoryExtent...])
  def __init__(self, extents):
    self._extents = extents

  @property
  def remaining(self):
    L = 0
    for extent in self._extents:
      L += extent.len
    return L

  def write(self, b):
    c = 0
    while len(b):
      if len(self._extents) == 0:
        return c

      extent = self._extents[0]
      n = min(len(b), extent.len)
      extent.copyTo(b[:n])
      c += n
      b = b[n:]

      if extent.len - n == 0:
        self._extents = self._extents[1:]
      else:
        self._extents[0] = self._extents[0][n:]

    return c
