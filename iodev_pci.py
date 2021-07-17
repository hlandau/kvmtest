from iodev import *

# A PCI bus-device-function value. This is a 16-bit integer of a format
# commonly used by PCI-related code and is formatted as follows:
#
#   bbbb bbbb  dddd dfff
#
# where b is the bus number, d is the device number and f is the function
# number.
#
# The most common presentation format for this is as follows:
#
#   BB:DD.F
#
# where BB, DD and F are hexadecimal representations of the bus, device and
# function numbers, respectively.
#
# To instantiate this class, pass a (bus, device, function) tuple or an integer
# containing the encoded BDF.
class BDF:
  __slots__ = ('_bdf',)

  def __new__(cls, bdf):
    if isinstance(bdf, BDF):
      return bdf

    return object.__new__(cls)

  def __init__(self, bdf):
    if type(bdf) == tuple:
      busNo, devNo, funcNo = bdf
      if busNo > 0xFF or devNo > 0x1F or funcNo > 0x7:
        raise Exception("bus, device or function number does not have a valid range: 0x%x, 0x%x, 0x%x" % (busNo, devNo, funcNo))

      self._bdf = (busNo<<8) | (devNo<<3) | funcNo

    elif type(bdf) == int:
      if bdf < 0 or bdf > 0xFFFF:
        raise Exception("not a valid BDF value: 0x%x" % bdf)

      self._bdf = bdf

    else:
      raise Exception("BDF argument must be a tuple or integer: %s" % (bdf,))

  @property
  def int(self):
    return self._bdf

  @property
  def tuple(self):
    funcNo = self._bdf        & 0x07
    devNo  = (self._bdf >> 3) & 0x1F
    busNo  = (self._bdf >> 8) & 0xFF
    return (busNo, devNo, funcNo)

  @property
  def busNo(self):
    return self.tuple[0]

  @property
  def devNo(self):
    return self.tuple[1]

  @property
  def funcNo(self):
    return self.tuple[2]

  def __repr__(self):
    return "%02x:%02x.%x" % self.tuple

# An entire PCI subsystem (PCI domain), which contains a set of PCI functions
# identified by their BDF.
class PciSubsystem:
  def __init__(self):
    self.bdfs = {}

  def insert(self, dev, bdf=None):
    if bdf is None:
      bdf = dev.bdf

    assert bdf is not None
    bdf = BDF(bdf)
    self.bdfs[bdf.int] = dev
    dev.pciSubsystem = self
    return dev

  def getConfig(self, bdf):
    dev = self.bdfs.get(bdf)
    if dev is None:
      return None
    return dev.config

  def cfgRead(self, bdf, reg):
    dev = self.bdfs.get(bdf)
    if dev is None:
      print("Warning: access to nonexistent PCI device %s (reg 0x%x)" % (BDF(bdf), reg))
      return 0xFFFFFFFF
    return dev.cfgRead(reg)

  def cfgWrite(self, bdf, reg, v):
    dev = self.bdfs.get(bdf)
    if dev is None:
      return
      #raise Exception("access to nonexistent PCI device %s (reg 0x%x)" % (self.formatBdf(bdf), reg))
    dev.cfgWrite(reg, v)

# A PCI function which can be made part of a PCI subsystem.
class PciFunctionBase:
  # Read a 32-bit PCI configuration register. The argument is the register
  # offset within the configuration space for the given BDF. Returns the result.
  #
  # (reg: u12) → (v: u32)
  def cfgRead(self, reg):
    raise NotImplementedError("%s does not support reading configuration register 0x%x" % reg)

  # Writes a 32-bit PCI configuration register. The argument is the register
  # offset within the configuration space for the given BDF.
  def cfgWrite(self, reg, v):
    raise NotImplementedError("%s does not support writing configuration register 0x%x (0x%x)" % (reg, v))

@registerDevice()
class PciConfig:
  base = 0
  len  = 4096

  def __init__(self, device):
    self.device = device

  vendorID              = Register16(0x00, get=lambda self: self.device.vendorID, ro=True)
  deviceID              = Register16(0x02, get=lambda self: self.device.deviceID, ro=True)
  command               = Register16(0x04)
  status                = Register16(0x06, ro=True)
  revision              = Register8 (0x08, get=lambda self: self.device.rev, ro=True)
  progIf                = Register8 (0x09, get=lambda self: self.device.progIf, ro=True)
  subclass              = Register8 (0x0A, get=lambda self: self.device.subClass, ro=True)
  classCode             = Register8 (0x0B, get=lambda self: self.device.classCode, ro=True)
  cacheLineSize         = Register8 (0x0C)
  latencyTimer          = Register8 (0x0D, ro=True)
  headerType            = Register8 (0x0E, ro=True)
  bist                  = Register8 (0x0F, ro=True)
  bar0                  = Register32(0x10, set=lambda self, v: self._setBar(0, v))
  bar1                  = Register32(0x14, set=lambda self, v: self._setBar(1, v))
  bar2                  = Register32(0x18, set=lambda self, v: self._setBar(2, v))
  bar3                  = Register32(0x1C, set=lambda self, v: self._setBar(3, v))
  bar4                  = Register32(0x20, set=lambda self, v: self._setBar(4, v))
  bar5                  = Register32(0x24, set=lambda self, v: self._setBar(5, v))
  cardbusCisPtr         = Register32(0x28, ro=True)
  subsystemVendorID     = Register16(0x2C, ro=True, get=lambda self: self.device.subsystemVendorID)
  subsystemID           = Register16(0x2E, ro=True, get=lambda self: self.device.subsystemID)
  expansionRomBaseAddr  = Register32(0x30)
  capPtr                = Register8 (0x34, ro=True)
  rsvd35                = Register8 (0x35, ro=True)
  rsvd36                = Register16(0x36, ro=True)
  rsvd38                = Register32(0x38, ro=True)
  intrLine              = Register8 (0x3C)
  intrPin               = Register8 (0x3D, ro=True)
  minGrant              = Register8 (0x3E, ro=True)
  maxLatency            = Register8 (0x3F, ro=True)

  def __repr__(self):
    return f"PciConfig(for device {repr(self.device)})"

  def _setBar(self, barNo, v):
    bars = self.device.bars
    if barNo >= len(bars) or bars[barNo] is None:
      return

    L, kind = bars[barNo]
    if kind == 'io':
      vv  = (v & 0xFFFF_FFFC)
      vv2 = vv | 1
    elif kind == 'm32':
      vv  = (v & 0xFFFF_FFF0)
      vv  = vv & ~(L-1)
      vv2 = vv
    else:
      raise NotImplementedError()

    getattr(self, 'bar%s' % barNo).value = vv2
    self.device.cfgBarChanged(barNo, vv)

class PciBar(MemoryHandler):
  base = 0xFFFFFFFF

class PciRamBar(PciBar):
  def __init__(self, device):
    self._device = device
    self._slot = None
    self._lock = None

  def onBarUpdate(self):
    if self._lock:
      self._lock.acquire()

    if self._slot:
      self._slot.teardown()
    self._slot = self._device._memoryManager.mapNew(self.base, self.len)

    if self._lock:
      self._lock.release()

# A PCI function with a Type 0 header which implements basic functionality for
# standard configuration registers.
class PciFunction(PciFunctionBase):
  configClass = PciConfig
  bars = (None, None, None, None, None, None)
  barHandlers = (None, None, None, None, None, None)
  subsystemID = 0
  subsystemVendorID = 0

  def __init__(self):
    self.config = self.configClass(self)

  def cfgRead(self, reg):
    return self.config.read32(reg)

  def cfgWrite(self, reg, v):
    return self.config.write32(reg, v)

  def cfgBarChanged(self, barNo, v):
    if self.barHandlers[barNo]:
      self.barHandlers[barNo].base = v
      if hasattr(self.barHandlers[barNo], 'onBarUpdate'):
        self.barHandlers[barNo].onBarUpdate()

  def addBarM32(self, barNo, handler):
    if type(self.bars) == tuple:
      self.bars         = list(self.bars)
      self.barHandlers  = list(self.barHandlers)

    self.bars[barNo]        = (handler.len, 'm32')
    self.barHandlers[barNo] = handler
    return handler

# An I/O port handler which implements the 0xCF8 and 0xCFC I/O ports for access
# to PCI configuration space. Must be given a PCI subsystem to work with.
@registerDevice()
class PciIoCfgDev(MemoryHandler):
  base = 0xCF8
  len  = 8

  cf8 = Register32(0, title='Address Port')
  cfc = Register32(4, title='Data Port')

  def __init__(self, pciSubsystem):
    self.pciSubsystem = pciSubsystem

  @cfc.getter
  def _(self):
    cf8 = self.cf8.value & 0x7FFF_FFFF
    bdf = cf8 >> 8
    reg = cf8 & 0xFF
    return self.pciSubsystem.cfgRead(bdf, reg)

  @cfc.setter
  def _(self, v):
    cf8 = self.cf8.value & 0x7FFF_FFFF
    bdf = cf8 >> 8
    reg = cf8 & 0xFF
    return self.pciSubsystem.cfgWrite(bdf, reg, v)

# A memory handler which implements the PCIe memory-mapped expanded
# configuration space.
class PciMmioCfgDev(MemoryHandler):
  base = 0xB000_0000
  len  = 0x1000_0000

  def __init__(self, pciSubsystem):
    self.pciSubsystem = pciSubsystem

  def split(self, addr):
    bdf = (addr>>12) & 0xFFFF
    reg = addr & 0xFFF
    config = self.pciSubsystem.getConfig(bdf)
    return config, reg

  def read32(self, addr):
    config, reg = self.split(addr)
    if config is None:
      return 0xFFFF_FFFF

    return config.read32(reg)

  def write32(self, addr, v):
    config, reg = self.split(addr)
    if config is None:
      return

    return config.write32(reg, v)

  def read16(self, addr):
    config, reg = self.split(addr)
    if config is None:
      return 0xFFFF

    return config.read16(reg)

  def write16(self, addr, v):
    config, reg = self.split(addr)
    if config is None:
      return

    return config.write16(reg, v)

  def read8(self, addr):
    config, reg = self.split(addr)
    if config is None:
      return 0xFF

    return config.read8(reg)

  def write8(self, addr, v):
    config, reg = self.split(addr)
    if config is None:
      return

    return config.write8(reg, v)
