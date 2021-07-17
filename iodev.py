# Abstract interface for objects which can handle memory accesses. "Memory" in
# this context can also mean e.g. I/O ports and the scope being accessed must
# be understood from the context.
class MemoryHandler:
  # (addr: u64) → u8 / u16 / u32 / u64
  def read8(self, addr):
    raise NotImplementedError("%s: read u8(0x%x)" % (self, addr))
  def read16(self, addr):
    raise NotImplementedError("%s: read u16(0x%x)" % (self, addr))
  def read32(self, addr):
    raise NotImplementedError("%s: read u32(0x%x)" % (self, addr))
  def read64(self, addr):
    raise NotImplementedError("%s: read u64(0x%x)" % (self, addr))

  # (addr: u64, v: u8 / u16 / u32 / u64) → ()
  def write8(self, addr, v):
    raise NotImplementedError("%s: write u8(0x%x): 0x%x" % (self, addr, v))
  def write16(self, addr, v):
    raise NotImplementedError("%s: write u16(0x%x): 0x%x" % (self, addr, v))
  def write32(self, addr, v):
    raise NotImplementedError("%s: write u32(0x%x): 0x%x" % (self, addr, v))
  def write64(self, addr, v):
    raise NotImplementedError("%s: write u64(0x%x): 0x%x" % (self, addr, v))

# MemoryHandler which can dispatch to other MemoryHandlers by range.
class AddressSpace(MemoryHandler):
  def __init__(self):
    self.mappings = []

  # Mount a new memory handler. The handler should contain attributes .base and
  # .len, which should designate the range of addresses handled [base,
  # base+len). Also returns the handler.
  def mount(self, handler):
    self.mappings.append(handler)
    return handler

  # Determines the memory handler which handles the given address and returns it.
  # Throws an exception if no memory handler for the address can be found.
  def resolve(self, addr):
    for handler in self.mappings:
      if addr >= handler.base and addr < (handler.base + handler.len):
        return handler

    raise Exception("%s: no mapping found for address 0x%x" % (self, addr))

  def read8(self, addr):
    return self.resolve(addr).read8(addr)
  def read16(self, addr):
    return self.resolve(addr).read16(addr)
  def read32(self, addr):
    return self.resolve(addr).read32(addr)
  def read64(self, addr):
    return self.resolve(addr).read64(addr)
  def write8(self, addr, v):
    return self.resolve(addr).write8(addr, v)
  def write16(self, addr, v):
    return self.resolve(addr).write16(addr, v)
  def write32(self, addr, v):
    return self.resolve(addr).write32(addr, v)
  def write64(self, addr, v):
    return self.resolve(addr).write64(addr, v)

#
def registerDevice():
  def f(cls):
    cls.__registers__ = []
    cls.__registersByOffset__ = {}
    for x in dir(cls):
      if x.startswith('_'):
        continue
      a = getattr(cls, x)
      if not isinstance(a, Register):
        continue

      a.key = x
      a.cls = cls
      cls.__registers__.append(a)
      for i in range((a.mapWidth+8)//8-1):
        cls.__registersByOffset__[a.offset+i] = a

    oldInit = None
    if hasattr(cls, '__init__'):
      oldInit = cls.__init__

    def init(self, *args, **kwargs):
      if not hasattr(self, '__registerInitDone__'):
        base = kwargs.get('base')
        if base is not None:
          self.base = base

        rs = []
        rbo = {}
        for r in self.__registers__:
          ri = r.instantiateOn(self)
          rs.append(ri)
          for i in range((r.mapWidth+8)//8-1):
            rbo[ri.offset+i] = ri
          setattr(self, r.key, ri)

        self.__registers__ = rs
        self.__registersByOffset__ = rbo
        self.__registerInitDone__ = True

      if oldInit is not None:
        oldInit(self, *args, **kwargs)

    init.isRegisterDeviceInit = True

    def read(self, addr, width):
      # A single read can read multiple actual registers (for example, a 32-bit
      # read of four 8-bit registers).
      curOffset = addr - self.base
      bitCount  = 0                 # Number of bits retrieved so far
      v         = 0
      while bitCount < width:
        ri = self.__registersByOffset__.get(curOffset)
        if ri is None:
          if hasattr(self, 'onUnknownRead'):
            return self.onUnknownRead(addr, width)
          raise Exception("%s: unknown register read: 0x%x (+0x%x) u%s (%x)" % (self, addr, addr - self.base, width, curOffset))

        relOffset   = curOffset - ri.offset # Offset in bytes into this register
        assert relOffset >= 0
        rw = width
        while rw > ri.width - relOffset*8:
          rw = rw // 2

        assert rw >= 8
        vv = ri.read(relOffset, rw)
        v = v | (vv << bitCount)

        curOffset += rw//8
        bitCount  += rw

      return v

      ri = self.__registersByOffset__.get(addr - self.base)
      if ri is None:
        raise Exception("%s: unknown register read: 0x%x (+0x%x) u%s" % (self, addr, addr-self.base, width))

      if ri.width < width:
        pass

      return ri.read(addr - self.base - ri.offset, width)

    def write(self, addr, v, width):
      # A single write can write multiple actual registers (for example, a 32-bit
      # write of four 8-bit registers).
      curOffset   = addr - self.base
      bitCount    = 0
      vv          = v
      oneSuccess  = False
      while bitCount < width:
        ri = self.__registersByOffset__.get(curOffset)
        if ri is None:
          if hasattr(self, 'onUnknownWrite'):
            return self.onUnknownWrite(addr, v, width)
          raise Exception("%s: unknown register write: 0x%x (+0x%x) u%s = 0x%x (0x%x)" % (self, addr, addr-self.base, width, v, curOffset))

        relOffset   = curOffset - ri.offset # Offset into bytes into this register
        assert relOffset >= 0
        rw = width
        while rw > ri.width - relOffset*8:
          rw = rw // 2

        assert rw >= 8

        if not ri.reg.ro:
          ri.write(relOffset, vv & bits0(rw-1), rw)
          oneSuccess = True

        vv = vv >> rw

        curOffset += rw//8
        bitCount  += rw

      if not oneSuccess:
        raise Exception("%s: all registers written were read-only: 0x%x (+0x%x) u%s = 0x%x" % (self, addr, addr-self.base, width, v))

    def read8(self, addr):
      return read(self, addr, 8)
    def read16(self, addr):
      return read(self, addr, 16)
    def read32(self, addr):
      return read(self, addr, 32)
    def read64(self, addr):
      return read(self, addr, 64)

    def write8(self, addr, v):
      return write(self, addr, v, 8)
    def write16(self, addr, v):
      return write(self, addr, v, 16)
    def write32(self, addr, v):
      return write(self, addr, v, 32)
    def write64(self, addr, v):
      return write(self, addr, v, 64)

    if not hasattr(cls, '__init__') or not hasattr(cls.__init__, 'isRegisterDeviceInit'):
      cls.__init__ = init

    cls.read8 = read8
    cls.read16 = read16
    cls.read32 = read32
    cls.read64 = read64
    cls.write8 = write8
    cls.write16 = write16
    cls.write32 = write32
    cls.write64 = write64
    return cls

  return f

class Register:
  def __init__(self, offset, abbr=None, *, set=None, get=None, afterSet=None, title=None, initial=0, ro=False, noOffset=False):
    self.offset = offset
    self.set      = set       # unbound function: (v) → ()
    self.get      = get       # unbound function: () → (v)
    self.afterSet = afterSet  # unbound function: (v) → ()
    self.abbr     = abbr
    self.title    = title
    self.initial  = initial
    self.ro       = ro
    self.noOffset = noOffset
    if self.noOffset:
      self.mapWidth = 8
    else:
      self.mapWidth = self.width
    assert self.width

  def getter(self, f):
    self.get = f # unbound function
    return f

  def setter(self, f):
    self.set = f # unbound function
    return f

  def afterSet(self, f):
    self.afterSet = f # unbound function
    return f

  def instantiateOn(self, obj):
    return RegisterInstance(self, obj, self.initial)

  def __repr__(self):
    return f"Register({self.key}: u{self.width})"

class Register8(Register):
  width = 8
class Register16(Register):
  width = 16
class Register32(Register):
  width = 32
class Register64(Register):
  width = 64

# bits 0:n
def bits0(n):
  return (1<<n) | ((1<<n)-1)

# bits n:m
def bits(n,m):
  assert n <= m
  v = bits0(m)
  if n > 0:
    v = v ^ bits0(n-1)
  return v

class RegisterInstance:
  def __init__(self, reg, obj, value=0):
    self.reg    = reg
    self.obj    = obj
    self.value  = value

  @property
  def offset(self):
    return self.reg.offset

  @property
  def width(self):
    return self.reg.width

  @property
  def mapWidth(self):
    return self.reg.mapWidth

  def read(self, offset, width):
    assert offset >= 0 and offset + width//8 <= self.reg.width//8

    if self.reg.get is not None:
      v = self.reg.get(self.obj)
    else:
      v = self.value

    return (v >> (offset*8)) & bits0(width-1)

  def write(self, offset, v, width):
    if self.reg.ro:
      raise Exception("cannot write read-only register: %s: +0x%x: u%s(0x%x)" % (self, offset, width, v))

    rw = self.reg.width
    assert offset >= 0 and offset + width//8 <= rw//8

    if width < rw:
      oldv = self.read(0, rw)

      wmask   = bits0(width-1)
      oshift  = offset*8
      vv = (oldv & ~(wmask<<oshift)) | ((v & wmask)<<oshift)
    else:
      assert width == rw
      vv = v & bits0(rw-1)

    if self.reg.set is not None:
      self.reg.set(self.obj, vv)
    else:
      self.value = vv

    if self.reg.afterSet is not None:
      self.reg.afterSet(self.obj, vv)

  def __repr__(self):
    return f"RegisterInstance(of {repr(self.reg)}, on {repr(self.obj)})"
