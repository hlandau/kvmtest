import struct, io
from iodev import *
from iodev_pci import *
from memmgr import *
from scsi import *

@registerDevice()
class VirtioScsiConfig(PciConfig):
  capCommon_id     = Register8 (0x40, ro=True, initial=0x09)
  capCommon_next   = Register8 (0x41, ro=True, initial=0x50)
  capCommon_clen   = Register8 (0x42, ro=True, initial=16)
  capCommon_type   = Register8 (0x43, ro=True, initial=1)
  capCommon_bar    = Register32(0x44, ro=True, initial=0) # low 8 bits are BAR index
  capCommon_offset = Register32(0x48, ro=True, initial=0)
  capCommon_len    = Register32(0x4C, ro=True, initial=0x38)

  capNotify_id     = Register8 (0x50, ro=True, initial=0x09)
  capNotify_next   = Register8 (0x51, ro=True, initial=0x64)
  capNotify_clen   = Register8 (0x52, ro=True, initial=20)
  capNotify_type   = Register8 (0x53, ro=True, initial=2)
  capNotify_bar    = Register32(0x54, ro=True, initial=0) # low 8 bits are BAR index
  capNotify_offset = Register32(0x58, ro=True, initial=0x70)
  capNotify_len    = Register32(0x5C, ro=True, initial=2)
  capNotify_mul    = Register32(0x60, ro=True, initial=2)

  capIsr_id     = Register8 (0x64, ro=True, initial=0x09)
  capIsr_next   = Register8 (0x65, ro=True, initial=0x74)
  capIsr_clen   = Register8 (0x66, ro=True, initial=16)
  capIsr_type   = Register8 (0x67, ro=True, initial=3)
  capIsr_bar    = Register32(0x68, ro=True, initial=0) # low 8 bits are BAR index
  capIsr_offset = Register32(0x6C, ro=True, initial=0x40)
  capIsr_len    = Register32(0x70, ro=True, initial=1)

  capDevice_id     = Register8 (0x74, ro=True, initial=0x09)
  capDevice_next   = Register8 (0x75, ro=True, initial=0x84)
  capDevice_clen   = Register8 (0x76, ro=True, initial=16)
  capDevice_type   = Register8 (0x77, ro=True, initial=4)
  capDevice_bar    = Register32(0x78, ro=True, initial=0) # low 8 bits are BAR index
  capDevice_offset = Register32(0x7C, ro=True, initial=0x44)
  capDevice_len    = Register32(0x80, ro=True, initial=0x24)

  capPci_id     = Register8 (0x84, ro=True, initial=0x09)
  capPci_next   = Register8 (0x85, ro=True, initial=0)
  capPci_clen   = Register8 (0x86, ro=True, initial=20)
  capPci_type   = Register8 (0x87, ro=True, initial=5)
  capPci_bar    = Register32(0x88, ro=True, initial=0) # low 8 bits are BAR index
  capPci_offset = Register32(0x8C, ro=True, initial=0)
  capPci_len    = Register32(0x90, ro=True, initial=0)
  capPci_data   = Register32(0x94, ro=True, initial=0)

  def __init__(self, device):
    super().__init__(device)
    self.capPtr.value = 0x40
    self.status.value = self.status.value | (1<<4)
    self.intrPin.value = 1

VIRTIO_F_RING_EVENT_IDX = 29
VIRTIO_F_VERSION_1      = 32

VIRTIO_SCSI_F_INOUT     = 0
VIRTIO_SCSI_F_HOTPLUG   = 1
VIRTIO_SCSI_F_CHANGE    = 2
VIRTIO_SCSI_F_T10_PI    = 3

VIRTIO_SCSI_S_OK                = 0
VIRTIO_SCSI_S_OVERRUN           = 1
VIRTIO_SCSI_S_ABORTED           = 2
VIRTIO_SCSI_S_BAD_TARGET        = 3
VIRTIO_SCSI_S_RESET             = 4
VIRTIO_SCSI_S_BUSY              = 5
VIRTIO_SCSI_S_TRANSPORT_FAILURE = 6
VIRTIO_SCSI_S_TARGET_FAILURE    = 7
VIRTIO_SCSI_S_NEXUS_FAILURE     = 8
VIRTIO_SCSI_S_FAILURE           = 9

@registerDevice()
class VirtioScsiBar0(PciBar):
  len = 4*1024

  comDevFeatSel = Register32(0x00)
  comDevFeat    = Register32(0x04, ro=True)
  comDrvFeatSel = Register32(0x08)
  comDrvFeat    = Register32(0x0C)
  comMsixCfg    = Register16(0x10)
  comNumQueue   = Register16(0x12, ro=True, initial=3)
  comDevStatus  = Register8 (0x14, afterSet=lambda self, v: self._onDevStatusChange(v))
  comCfgGen     = Register8 (0x15, ro=True)

  comQueueSel         = Register16(0x16)
  comQueueLen         = Register16(0x18)
  comQueueMsixVector  = Register16(0x1A)
  comQueueEnable      = Register16(0x1C)
  comQueueNotifyOff   = Register16(0x1E, ro=True)
  comQueueDesc        = Register64(0x20)
  comQueueDrv         = Register64(0x28)
  comQueueDev         = Register64(0x30)

  isrStatus           = Register8 (0x40, ro=True)

  scsiNumQueue        = Register32(0x44, ro=True, initial=1)
  scsiSegMax          = Register32(0x48, ro=True, initial=4)
  scsiMaxSectors      = Register32(0x4C, ro=True, initial=128*1024)
  scsiCmdPerLun       = Register32(0x50, ro=True, initial=16)
  scsiEventInfoLen    = Register32(0x54, ro=True)
  scsiSenseLen        = Register32(0x58, initial=96)
  scsiCdbLen          = Register32(0x5C, initial=32)
  scsiMaxChannel      = Register16(0x60, ro=True)
  scsiMaxTarget       = Register16(0x62, ro=True, initial=1)
  scsiMaxLun          = Register32(0x64, ro=True, initial=1)

  notify0             = Register16(0x70, set=lambda self, v: self._onNotify(v))

  @comDevFeat.getter
  def _(self):
    pageNo = self.comDevFeatSel.value
    v = 0
    for i in range(32):
      if self._getDevFeature(pageNo*32 + i):
        v = v|(1<<i)

    return v

  @comDrvFeat.getter
  def _(self):
    pageNo = self.comDrvFeatSel.value
    for i in range(32):
      if self._getDrvFeature(pageNo*32 + i):
        v = v|(1<<i)

    return v

  @comDrvFeat.setter
  def _(self, v):
    pageNo = self.comDrvFeatSel.value
    for i in range(32):
      self._setDrvFeature(pageNo*32 + i, bool(v & (1<<i)))

  def _getDevFeature(self, n):
    return n in (VIRTIO_F_VERSION_1, VIRTIO_SCSI_F_INOUT)

  def _getDrvFeature(self, n):
    return False

  def _setDrvFeature(self, n, on):
    print('@Virtio: feature %s on=%s' % (n, on))

  def _onDevStatusChange(self, v):
    print('@Virtio: dev status=0x%x' % v)
    if v == 0:
      print('@Virtio: resetting device')
      self._reset()

  @comQueueLen.getter
  def _(self):
    queueNo = self.comQueueSel.value
    if queueNo >= len(self._queueLens):
      return 0

    return self._queueLens[queueNo]

  @comQueueLen.setter
  def _(self, v):
    queueNo = self.comQueueSel.value
    if queueNo >= len(self._queueLens):
      return

    self._queueLens[queueNo] = min(v, self._maxQueueLens[queueNo])

  @comQueueEnable.getter
  def _(self):
    queueNo = self.comQueueSel.value
    if queueNo >= len(self._queueEnables):
      return 0

    return int(self._queueEnables[queueNo])

  @comQueueEnable.setter
  def _(self, v):
    queueNo = self.comQueueSel.value
    if queueNo >= len(self._queueEnables):
      return

    self._queueEnables[queueNo] = bool(v)

  @comQueueDesc.getter
  def _(self):
    queueNo = self.comQueueSel.value
    if queueNo >= len(self._queueEnables):
      return

    return self._queueDescriptorAreas[queueNo]

  @comQueueDesc.setter
  def _(self, v):
    queueNo = self.comQueueSel.value
    if queueNo >= len(self._queueEnables):
      return

    self._setQueueDescriptorArea(queueNo, v)

  @comQueueDrv.getter
  def _(self):
    queueNo = self.comQueueSel.value
    if queueNo >= len(self._queueEnables):
      return

    return self._queueDriverAreas[queueNo]

  @comQueueDrv.setter
  def _(self, v):
    queueNo = self.comQueueSel.value
    if queueNo >= len(self._queueEnables):
      return

    self._setQueueDriverArea(queueNo, v)

  @comQueueDev.getter
  def _(self):
    queueNo = self.comQueueSel.value
    if queueNo >= len(self._queueEnables):
      return

    return self._queueDeviceAreas[queueNo]

  @comQueueDev.setter
  def _(self, v):
    queueNo = self.comQueueSel.value
    if queueNo >= len(self._queueEnables):
      return

    self._setQueueDeviceArea(queueNo, v)

  @isrStatus.getter
  def _(self):
    v = self.isrStatus.value
    self.isrStatus.value = 0
    self._updateIntr()
    return v

  def _assertQueueIntr(self):
    self.isrStatus.value = self.isrStatus.value | (1<<0)
    self._updateIntr()

  def _updateIntr(self):
    self._device.pciSubsystem._vm.setIrqLine(self._device.config.intrLine.value, bool(self.isrStatus.value))

  def _onNotify(self, queueIdx):
    if queueIdx >= len(self._queueLens):
      return

    self._syncProcessAvail(queueIdx)

  def _setQueueDescriptorArea(self, queueNo, v):
    self._queueDescriptorAreas[queueNo] = v

  def _setQueueDriverArea(self, queueNo, v):
    self._queueDriverAreas[queueNo] = v

  def _setQueueDeviceArea(self, queueNo, v):
    self._queueDeviceAreas[queueNo] = v

  def _syncProcessAvail(self, queueNo):
    queueLen    = self._queueLens[queueNo]
    pAvailRing  = self._queueDriverAreas[queueNo]

    avails = self._device._memoryManager.read(pAvailRing, 2+2+2*queueLen+2)
    if avails is None:
      print('@Virtio: cannot get buffer for avail ring 0x%x' % pAvailRing)
      return

    availFlags, availIdx = struct.unpack('<HH', avails[0:4])

    curAvailIdx = self._queueAvailIdx[queueNo]
    while curAvailIdx != availIdx:
      headDescIdx = struct.unpack('<H', avails[4+2*(curAvailIdx%queueLen):4+2*(curAvailIdx%queueLen)+2])[0]
      curAvailIdx = (curAvailIdx+1) & 0xFFFF
      self._syncProcessDescriptor(queueNo, headDescIdx)

    self._queueAvailIdx[queueNo] = curAvailIdx

  def _syncProcessDescriptor(self, queueNo, headDescIdx):
    queueLen      = self._queueLens[queueNo]
    pDescriptors  = self._queueDescriptorAreas[queueNo]

    curDescIdx  = headDescIdx
    readBufs    = []
    writeBufs   = []

    while True:
      if curDescIdx >= queueLen:
        print('@Virtio: invalid descriptor index 0x%x' % headDescIdx)
        return

      descBuf = self._device._memoryManager.read(pDescriptors + 16*(curDescIdx%queueLen), 16)
      if descBuf is None:
        print('@Virtio: cannot get buffer for desc 0x%x' % headDescIdx)
        return

      dAddr, dLen, dFlags, dNext = struct.unpack('<QIHH', descBuf)
      print('@Virtio: DESC 0x%04x: a=0x%x L=0x%x flags=0x%x next=0x%x' % (curDescIdx, dAddr, dLen, dFlags, dNext))
      if dFlags & 4: # INDIRECT
        raise Exception("indirect descriptors not supported")

      isWrite = bool(dFlags & 2)
      extents = self._device._memoryManager.resolveExtents(dAddr, dLen)
      if isWrite:
        writeBufs += extents
      else:
        readBufs += extents

      curDescIdx = dNext
      if (dFlags & 1) == 0:
        break

    rbuf = MultiReadBuffer(readBufs)
    wbuf = MultiWriteBuffer(writeBufs)
    wbufLen = wbuf.remaining
    self._syncProcessBuffers(queueNo, rbuf, wbuf)
    self._syncProcessUsed(queueNo, headDescIdx, wbufLen - wbuf.remaining)

  def _syncProcessUsed(self, queueNo, headDescIdx, totalWritten):
    queueLen  = self._queueLens[queueNo]
    pUsedRing = self._queueDeviceAreas[queueNo]
    curUsedIdx = self._queueUsedIdx[queueNo]

    self._device._memoryManager.write(pUsedRing+2+2+8*(curUsedIdx%queueLen), struct.pack('<II', headDescIdx, totalWritten))
    self._device._memoryManager.write(pUsedRing+2, struct.pack('<H', (curUsedIdx+1) & 0xFFFF))

    #usedAddr, usedLen = self._device._memoryManager.resolveAddr(pUsedRing)
    #if usedLen < 2+2+8*queueLen:
    #  raise Exception("used ring must be in one allocation")

    #copyToRam(usedAddr+2+2+2*curUsedIdx, struct.pack('<II', headDescIdx, totalWritten))
    #copyToRam(usedAddr+2, struct.pack('<H', curUsedIdx+1))
    self._queueUsedIdx[queueNo] = (curUsedIdx+1) & 0xFFFF
    self._assertQueueIntr()
    print('@Virtio: DONE 0x%x (q %s, written %s bytes) cuidx=0x%x ql=%s' % (headDescIdx, queueNo, totalWritten, curUsedIdx, queueLen))

  def _syncProcessBuffers(self, queueNo, rbuf, wbuf):
    reqL = 8+8+1+1+1+self.scsiCdbLen.value
    req = rbuf.read(reqL)
    if len(req) < reqL:
      raise Exception("short SCSI request")

    lun = struct.unpack('>Q', req[0:8])[0]
    id, taskAttr, priority, crn = struct.unpack('<QBBB', req[8:19])
    print('@Virtio: SCSI request: LUN=0x%x, ID=%s, cdb.opcode=0x%x' % (lun, id, req[19]))
    cdb = req[19:19+self.scsiCdbLen.value]

    dataOutBuf = None
    if rbuf.remaining:
      dataOutBuf      = rbuf
      dataOutBuf.len  = rbuf.remaining

    dataInBuf = None
    if wbuf.remaining:
      dataInBuf     = io.BytesIO()
      dataInBuf.len = wbuf.remaining

    cmd = ScsiCmd(lun=lun, id=id, cdb=cdb, taskAttr=taskAttr, crn=crn, priority=priority,
      dataOutBuf=dataOutBuf, dataInBuf=dataInBuf)
    try:
      res = self._device.scsiSubsystem.executeCommand(cmd)
      residual = 0
      senseLen = 0
      if res.senseData is not None:
        senseLen = len(res.senseData)
      wbuf.write(struct.pack('<IIHBB', senseLen, residual, res.statusQualifier or 0, res.status, VIRTIO_SCSI_S_OK))
      wbuf.write((res.senseData or b'').ljust(self.scsiSenseLen.value, b'\0'))
      if dataInBuf is not None:
        L = 0
        dataInBuf.seek(0)
        while True:
          if L >= dataInBuf.len:
            break
          d = dataInBuf.read(min(8192, dataInBuf.len - L))
          if d == b'':
            break
          wbuf.write(d)
          L += len(d)
          #print('@Virtio: writing %s bytes to data-in: %s (rem 0x%x)' % (len(d),d, wbuf.remaining))
    except Exception as e:
      print('@Virtio: SCSI exception: %s' % e)
      wbuf.write(struct.pack('<IIHBB', 0, 0, 0, 0, VIRTIO_SCSI_S_TARGET_FAILURE))

  def _reset(self):
    self._queueLens    = list(self._maxQueueLens)
    self._queueEnables = [False]*3
    self._queueDescriptorAreas = [0]*3
    self._queueDriverAreas = [0]*3
    self._queueDeviceAreas = [0]*3
    self._queueAvailIdx = [0]*3
    self._queueUsedIdx = [0]*3

  def __init__(self, device):
    self._device  = device
    self._maxQueueLens = (16,)*3
    self._reset()

class VirtioScsi(PciFunction):
  configClass       = VirtioScsiConfig
  bdf               = (0,2,0)
  vendorID          = 0x1af4
  deviceID          = 0x1048
  classCode         = 0
  subClass          = 0
  progIf            = 0
  rev               = 1
  subsystemVendorID = 0x1af4
  subsystemID       = 0x0048

  def __init__(self, memoryManager, scsiSubsystem):
    super().__init__()
    self._memoryManager = memoryManager
    self.scsiSubsystem = scsiSubsystem
    self.b0h = self.addBarM32(0, VirtioScsiBar0(self))
