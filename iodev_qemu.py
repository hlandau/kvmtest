import sys, struct
from iodev import *
from iodev_pci import *
from iodev_pc import *
from iodev_acpi import *
from iodev_tpm import *
from iodev_virtio import *
from memmgr import *
from scsi import *
import sdl2

@registerDevice()
class QemuDebugOutputDev(MemoryHandler):
  base = 0x402
  len  = 1

  r402 = Register8(0, initial=0xE9)

  def __init__(self):
    self._dbgStr = []

  @r402.setter
  def _(self, v):
    self._dbgStr.append(v & 0xFF)
    if v == 10: # NL
      sys.stdout.write('DBG: %s' % bytes(self._dbgStr).decode('utf-8'))
      sys.stdout.flush()
      self._dbgStr = []

@registerDevice()
class QemuFwCfg(MemoryHandler):
  base = 0x510
  len  = 2

  sel  = Register16(0, noOffset=True, afterSet=lambda self, v: self._changeBuffer(v))
  data = Register8 (1, ro=True, get=lambda self: self._readBuffer())

  def _changeBuffer(self, v):
    print('Changing to buffer 0x%x' % v)
    self._buf = self._genBuffer(v)

  def _genBuffer(self, sel):
    return b''

  def _readBuffer(self):
    if len(self._buf) == 0:
      return 0

    v = self._buf[0]
    self._buf = self._buf[1:]
    return v

@registerDevice()
class Q35PciIch9Config(PciConfig):
  pciexbarLo  = Register32(0x60)
  pciexbarHi  = Register32(0x64)
  pam1        = Register8 (0x91)

class Q35PciIch9(PciFunction):
  configClass = Q35PciIch9Config
  bdf         = (0,0,0)
  vendorID    = 0x8086
  deviceID    = 0x29c0 # INTEL_Q35_MCH_DEVICE_ID
  classCode   = 0
  subClass    = 0
  progIf      = 0
  rev         = 0

@registerDevice()
class Q35PciD31F0Config(PciConfig):
  pmbase    = Register32(0x40, afterSet=lambda self, v: print('PMBASE=0x%x' % v))
  acpiCntl  = Register32(0x44, afterSet=lambda self, v: print('ACPICTL=0x%x' % v))
  rcr1      = Register32(0x60)
  rcr2      = Register32(0x68)
  rcba      = Register32(0xF0)

class Q35PciD31F0(PciFunction):
  configClass = Q35PciD31F0Config
  bdf         = (0,31,0)
  vendorID    = 0x8086
  deviceID    = 0x7000
  classCode   = 0x06 # Bridge: ISA Bridge
  subClass    = 0x01 #
  progIf      = 0x00 #
  rev         = 0x55

@registerDevice()
class QxlRegs(MemoryHandler):
  base = 0
  len  = 0xFFFF

  id        = Register16(0x00, initial=0xB0C0, ro=True, noOffset=True)
  xRes      = Register16(0x01, noOffset=True, afterSet=lambda self,v : self.onModeChange())
  yRes      = Register16(0x02, noOffset=True, afterSet=lambda self, v: self.onModeChange())
  bpp       = Register16(0x03, noOffset=True, afterSet=lambda self, v: self.onModeChange())
  enable    = Register16(0x04, noOffset=True, afterSet=lambda self, v: self.onModeChange())
  bank      = Register16(0x05, noOffset=True, afterSet=lambda self, v: self.onModeChange())
  virtWidth = Register16(0x06, noOffset=True, afterSet=lambda self, v: self.onModeChange())
  virtHeight= Register16(0x07, noOffset=True, afterSet=lambda self, v: self.onModeChange())
  xOffset   = Register16(0x08, noOffset=True, afterSet=lambda self, v: self.onModeChange())
  yOffset   = Register16(0x09, noOffset=True, afterSet=lambda self, v: self.onModeChange())

  def __init__(self, qxl):
    self._qxl = qxl

  def onModeChange(self):
    e = sdl2.SDL_Event()
    e.type = getSdlSyncEventNo()
    print('@ModeChange:Event 0x%x' % e.type)
    sdl2.SDL_PushEvent(e)

@registerDevice()
class QxlIo(MemoryHandler):
  base = 0x1CE
  len  = 4

  addr  = Register16(0)
  data  = Register16(2)

  def __init__(self, qxl):
    self._qxl = qxl

  @data.getter
  def _(self):
    return self._qxl._regs.read16(self.addr.value)

  @data.setter
  def _(self, v):
    return self._qxl._regs.write16(self.addr.value, v)

@registerDevice()
class QxlVgaIo(MemoryHandler):
  base = 0x3C0
  len  = 17

  def __init__(self, qxl):
    self._qxl = qxl

  attAddr     = Register8(0)
  paletteIdx  = Register8(0x8)
  paletteData = Register8(0x9)

class QxlBar0(PciRamBar):
  len   = 16*1024*1024

@registerDevice()
class QxlBar2(MemoryHandler):
  base  = 0xFFFFFFFF
  len   = 8*1024

  def __init__(self, device):
    self._device = device

  magic           = Register32(0x00, ro=True, initial=0x4f52_5851)
  drawStart       = Register32(0x24, ro=True)
  availableFBSize = Register32(0x28, ro=True, initial=(16*1024*1024))

def getSdlSyncEventNo():
  v = None
  def f():
    nonlocal v
    if v is None:
      v = sdl2.SDL_RegisterEvents(1)
    return v
  return f

getSdlSyncEventNo = getSdlSyncEventNo()

class Qxl(PciFunction):
  bdf       = (0,1,0)
  vendorID  = 0x1B36
  deviceID  = 0x0100
  classCode = 0x03 # Display
  subClass  = 0x00 # VGA-compatible
  progIf    = 0x00
  rev       = 0

  def __init__(self, memoryManager):
    super().__init__()
    self._memoryManager = memoryManager
    self._regs   = QxlRegs(self)
    self.io      = QxlIo(self)
    self.vgaIo   = QxlVgaIo(self)
    self.b0h     = self.addBarM32(0, QxlBar0(self))
    self.b2h     = self.addBarM32(2, QxlBar2(self))
    self.keyEventHandler = None

    self._startVisualizer()

  def teardown(self):
    self._visRun = False
    self._visExitLock.acquire()

  def _startVisualizer(self):
    import threading, sdl2, ctypes

    self._visRun = True

    lock = threading.Lock()
    self.b0h._lock = lock

    exitLock = threading.Lock()
    exitLock.acquire()
    self._visExitLock = exitLock

    def f():
      sdl2.SDL_Init(sdl2.SDL_INIT_VIDEO)

      w = sdl2.SDL_CreateWindow(b"Framebuffer", sdl2.SDL_WINDOWPOS_UNDEFINED, sdl2.SDL_WINDOWPOS_UNDEFINED, 800, 600, sdl2.SDL_WINDOW_SHOWN)
      s = None
      curUserspaceAddr = None

      def onModeChange():
        nonlocal s, curUserspaceAddr
        if s is not None:
          sdl2.SDL_FreeSurface(s)
          s = None

        if self.b0h._slot is None or self._regs.virtWidth.value == 0 or self._regs.virtHeight.value == 0:
          print('@Mode Change: None (%s, %s, %s)' % (self.b0h._slot, self._regs.virtWidth.value, self._regs.virtHeight.value))
          sdl2.SDL_SetWindowTitle(w, b'Framebuffer')
          curUserspaceAddr = None
          return

        print('@Mode Change: w=%s, h=%s, bpp=%s' % (self._regs.virtWidth.value, self._regs.virtHeight.value, self._regs.bpp.value))

        sdl2.SDL_SetWindowSize(w, self._regs.virtWidth.value, self._regs.virtHeight.value)
        sdl2.SDL_SetWindowTitle(w, ("Framebuffer (%sx%sx%s)" % (self._regs.virtWidth.value, self._regs.virtHeight.value, self._regs.bpp.value)).encode('utf-8'))
        curUserspaceAddr = self.b0h._slot.userspaceAddr
        s = sdl2.SDL_CreateRGBSurfaceFrom(curUserspaceAddr,
            self._regs.virtWidth.value,
            self._regs.virtHeight.value,
            self._regs.bpp.value,
            (self._regs.virtWidth.value * self._regs.bpp.value) // 8,
            0x00FF_0000, 0x0000_FF00, 0x0000_00FF, 0x0000_0000)

      lock.acquire()
      onModeChange()
      lock.release()

      e = sdl2.SDL_Event()
      def handleEvent():
        if e.type == getSdlSyncEventNo():
          lock.acquire()
          onModeChange()
          lock.release()
        elif e.type == sdl2.SDL_KEYDOWN or e.type == sdl2.SDL_KEYUP:
          if self.keyEventHandler:
            self.keyEventHandler(e)

      while self._visRun:
        if sdl2.SDL_WaitEventTimeout(ctypes.byref(e), 16) != 0:
          handleEvent()
          while sdl2.SDL_PollEvent(ctypes.byref(e)) != 0:
            handleEvent()

        lock.acquire()
        if (curUserspaceAddr and self.b0h._slot is None) or (self.b0h._slot and curUserspaceAddr != self.b0h._slot.userspaceAddr):
          onModeChange()

        dsts = sdl2.SDL_GetWindowSurface(w)
        if s is not None and dsts is not None:
          sdl2.SDL_BlitSurface(s, None, dsts, None)

        lock.release()
        sdl2.SDL_UpdateWindowSurface(w)

      if s:
        sdl2.SDL_FreeSurface(s)
        s = None

      sdl2.SDL_DestroyWindow(w)
      sdl2.SDL_Quit()
      exitLock.release()

    self._visThread = threading.Thread(target=f, name='QxlVis')
    self._visThread.daemon = True
    self._visThread.start()

class Q35PciSubsystem(PciSubsystem):
  def __init__(self, memoryManager, vm, scsiSubsystem):
    super().__init__()
    self.ich9       = self.insert(Q35PciIch9())
    self.ich9d31f0  = self.insert(Q35PciD31F0())
    self.qxl        = self.insert(Qxl(memoryManager))
    self.vioScsi    = self.insert(VirtioScsi(memoryManager, scsiSubsystem))
    self._vm        = vm

class Q35IOAddressSpace(AddressSpace):
  def __init__(self, platform, pciSubsystem, vm):
    super().__init__()

    self.qemuDebugOut = self.mount(QemuDebugOutputDev())
    self.qemuFwCfg    = self.mount(QemuFwCfg())
    self.pciCfgAccess = self.mount(PciIoCfgDev(pciSubsystem))
    self.rtc          = self.mount(Rtc())
    self.port92       = self.mount(Port92())
    self.pm           = self.mount(Q35PmIo())
    self.com1         = self.mount(SerialIo(0))
    self.com2         = self.mount(SerialIo(1))
    self.com3         = self.mount(SerialIo(2))
    self.com4         = self.mount(SerialIo(3))
    self.ps2          = self.mount(PS2Io(vm, sysResetFunc=platform.sysReset))
    self.qxl          = self.mount(pciSubsystem.qxl.io)
    self.vga          = self.mount(pciSubsystem.qxl.vgaIo)
    self.port80       = self.mount(Port80())

class Ram(MemoryHandler):
  base = 0
  len = 0

  def __init__(self, memoryManager, firmwarePath):
    self._memoryManager = memoryManager

    data = open(firmwarePath, 'rb').read()
    dataShortLen = min(len(data), 128*1024)
    assert len(data) <= 4*1024*1024
    assert (len(data) % 4096) == 0

    self._slot    = memoryManager.mapNew(0,                              1*1024*1024*1024)
    self._fwSlot  = memoryManager.mapNew(4*1024*1024*1024 - len(data), len(data), ro=True)

    self._memoryManager.write(0x10_0000 - dataShortLen, data[-dataShortLen:])
    self._memoryManager.write(4*1024*1024*1024 - len(data), data)

SYS_FLASH_STATE__NORMAL               = 0
SYS_FLASH_STATE__READ_STATUS_REG      = 1
SYS_FLASH_STATE__SINGLE_BYTE_PROGRAM  = 2

class SysFlash(MemoryHandler):
  base = 0
  len  = 0

  def __init__(self, memoryManager, firmwareVarsPath):
    self._f = open(firmwareVarsPath, 'r+b')
    self._data = bytearray(self._f.read())
    self.base = 0xFFC0_0000
    self.len = len(self._data)
    self._state   = SYS_FLASH_STATE__NORMAL
    self._wstate  = 0
    self._status  = 0

  def read8(self, addr):
    addr -= self.base
    print('@Flash read u8 0x%x' % addr)
    if self._state == SYS_FLASH_STATE__NORMAL:
      return self._data[addr]
    elif self._state == SYS_FLASH_STATE__READ_STATUS_REG:
      return self._status & 0xFF
    else:
      assert False

  def read16(self, addr):
    addr -= self.base
    print('@Flash read u16 0x%x' % addr)
    if self._state == SYS_FLASH_STATE__NORMAL:
      return struct.unpack('<H', self._data[addr:addr+2])[0]
    else:
      assert False

  def read32(self, addr):
    addr -= self.base
    print('@Flash read u32 0x%x' % addr)
    if self._state == SYS_FLASH_STATE__NORMAL:
      return struct.unpack('<I', self._data[addr:addr+4])[0]
    else:
      assert False

  def read64(self, addr):
    addr -= self.base
    print('@Flash read u64 0x%x' % addr)
    if self._state == SYS_FLASH_STATE__NORMAL:
      return struct.unpack('<Q', self._data[addr:addr+8])[0]
    else:
      assert False

  # '89AB01234567'
  def write8(self, addr, v):
    addr -= self.base
    print('@Flash write u8 0x%x = 0x%x' % (addr, v))
    if self._wstate == 0:
      if v == 0x10: # Single byte program
        self._state   = SYS_FLASH_STATE__SINGLE_BYTE_PROGRAM
        self._wstate  = 1
      elif v == 0x50: # Clear status bits
        self._status  = 0
        self._state   = SYS_FLASH_STATE__NORMAL
      elif v == 0x70: # Read status register
        self._state   = SYS_FLASH_STATE__READ_STATUS_REG
      elif v == 0xFF: # Read array mode
        self._state   = SYS_FLASH_STATE__NORMAL
      else:
        raise NotImplementedError("unsupported flash command 0x%x" % v)
    elif self._wstate == 1:
      if self._state == SYS_FLASH_STATE__SINGLE_BYTE_PROGRAM:
        self._wstate = 0
        self._status = self._status | 0x80
        self._setByte(addr, v)
      else:
        assert False
    else:
      assert False

  def _setByte(self, addr, v):
    self._data[addr] = v
    print('@FL [0x%x] = 0x%x' % (addr, v))
    self._f.seek(addr)
    self._f.write(bytes([v]))

class Q35MemoryAddressSpace(AddressSpace):
  def __init__(self, pciSubsystem, memoryManager, firmwarePath, firmwareVarsPath):
    super().__init__()

    self.tpmTis       = self.mount(TpmTis())
    self.pciCfgAccess = self.mount(PciMmioCfgDev(pciSubsystem))
    self.qxlBar0      = self.mount(pciSubsystem.qxl.b0h)
    self.qxlBar2      = self.mount(pciSubsystem.qxl.b2h)
    self.vioScsiBar0  = self.mount(pciSubsystem.vioScsi.b0h)
    self.ram          = self.mount(Ram(memoryManager, firmwarePath))
    self.sysFlash     = self.mount(SysFlash(memoryManager, firmwareVarsPath))

class Q35Platform:
  def __init__(self, *, memoryManager, firmwarePath, firmwareVarsPath, vm, sysResetFunc, opticalPath=None, diskPath=None):
    self.memoryManager    = memoryManager
    self.firmwarePath     = firmwarePath
    self.firmwareVarsPath = firmwareVarsPath
    self.vm               = vm
    self._sysResetFunc    = sysResetFunc
    self._opticalPath     = opticalPath
    self._diskPath        = diskPath
    self._reset()

  def _reset(self):
    self.scsiSubsystem  = ScsiSubsystem(opticalPath=self._opticalPath, diskPath=self._diskPath)
    self.pciSubsystem   = Q35PciSubsystem(self.memoryManager, self.vm, self.scsiSubsystem)
    self.iospace        = Q35IOAddressSpace(self, self.pciSubsystem, self.vm)
    self.mspace         = Q35MemoryAddressSpace(self.pciSubsystem, self.memoryManager, self.firmwarePath, self.firmwareVarsPath)

    def onKey(e):
      if e.type == sdl2.SDL_KEYDOWN:
        self.iospace.ps2.keyboard.keyDown(e.key.keysym.scancode)
      elif e.type == sdl2.SDL_KEYUP:
        self.iospace.ps2.keyboard.keyUp(e.key.keysym.scancode)

    self.pciSubsystem.qxl.keyEventHandler = onKey

  def sysReset(self):
    print('System reset')
    self.pciSubsystem.qxl.teardown()
    self._sysResetFunc()
    self._reset()
