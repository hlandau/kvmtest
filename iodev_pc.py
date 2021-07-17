import sys, re
from iodev import *

re_ansiEsc = re.compile(r'''\x1B\[[^a-zA-Z]*[a-zA-Z]''')

@registerDevice()
class Port92(MemoryHandler):
  base = 0x92
  len  = 1

  r = Register8(0, set=lambda self, v: ())

@registerDevice()
class Port80(MemoryHandler):
  base = 0x80
  len  = 16

  r00 = Register8(0x00, set=lambda self, v: ()) # Linux io_delay.c
  r07 = Register8(0x07, ro=True, initial=0xFF)  # Linux i8237.c

@registerDevice()
class Rtc(MemoryHandler):
  base = 0x70
  len  = 2

  addr = Register8(0, title='Address Port')
  data = Register8(1, title='Data Port')

  def __init__(self):
    self.actual = RtcActual(self)

  @data.getter
  def _(self):
    return self.actual.read8(self.addr.value)

  @data.setter
  def _(self, v):
    return self.actual.write8(self.addr.value, v)

@registerDevice()
class RtcActual(MemoryHandler):
  base = 0
  len  = 0xFF

  def __init__(self, rtc):
    self.rtc = rtc
    self.totalMem = (1*1024*1024*1024 - 16*1024*1024)//(64*1024)

  reg0B = Register8(0x0B, initial=2)
  reg0C = Register8(0x0C, initial=0, ro=True)
  reg0D = Register8(0x0D, initial=0x80, set=lambda self, v: ())
  reg34 = Register16(0x34, ro=True, get=lambda self: self.totalMem)

  def onUnknownRead(self, addr, width):
    print('RTC get: 0x%x u%s' % (addr, width))
    return 0

  def onUnknownWrite(self, addr, v, width):
    print('RTC set: 0x%x <- u%s(0x%x)' % (addr, width, v))

@registerDevice()
class SerialIo(MemoryHandler):
  base = 0x3F8
  len  = 8

  dr  = Register8(0x00)
  ier = Register8(0x01)
  fcr = Register8(0x02)
  lcr = Register8(0x03)
  mcr = Register8(0x04)
  lsr = Register8(0x05, ro=True, initial=(1<<5)|(1<<6)) # THRE|TEMT
  msr = Register8(0x06, ro=True, initial=0xB0)
  scr = Register8(0x07)

  _div = 0

  def __init__(self, n):
    self._n = n
    self._buf = []
    if n == 0:
      pass
    elif n == 1:
      self.base = 0x2f8
    elif n == 2:
      self.base = 0x3e8
    elif n == 3:
      self.base = 0x2e8
    else:
      raise Exception("...")

  @dr.getter
  def _(self):
    if self.lcr.value & 0x80:
      return self._div & 0xFF
    else:
      return 0

  @dr.setter
  def _(self, v):
    if self.lcr.value & 0x80:
      self._div = (self._div & 0xFF00) | v
    else:
      self._outputChar(v)

  @ier.getter
  def _(self):
    if self.lcr.value & 0x80:
      return self._div >> 8
    else:
      return self.ier.value

  @ier.setter
  def _(self, v):
    if self.lcr.value & 0x80:
      self._div = (self._div & 0xFF) | (v<<8)
    else:
      self.ier.value = v

  def _outputChar(self, v):
    self._buf.append(v)
    if v == 10:
      sys.stdout.write('COM%s: %s' % (self._n+1, re_ansiEsc.sub('', bytes(self._buf).decode('ascii', errors='ignore'))))
      sys.stdout.flush()
      self._buf = []

class PS2Device:
  def reset(self):
    pass

  def poll(self):
    return False

  def read(self):
    return None

  def write(self, v):
    pass

PS2_KEYBOARD_STATE__NORMAL        = 0
PS2_KEYBOARD_STATE__SET_SCANCODE  = 1
PS2_KEYBOARD_STATE__SET_REPEAT    = 2
PS2_KEYBOARD_STATE__SET_LED       = 3

_usbToScancodeSet2 = {
  0x04: (b'\x1C', b'\xF0\x1C'), # 'A'
  0x05: (b'\x32', b'\xF0\x32'), # 'B'
  0x06: (b'\x21', b'\xF0\x21'), # 'C'
  0x07: (b'\x23', b'\xF0\x23'), # 'D'
  0x08: (b'\x24', b'\xF0\x24'), # 'E'
  0x09: (b'\x2B', b'\xF0\x2B'), # 'F'
  0x0A: (b'\x34', b'\xF0\x34'), # 'G'
  0x0B: (b'\x33', b'\xF0\x33'), # 'H'
  0x0C: (b'\x43', b'\xF0\x43'), # 'I'
  0x0D: (b'\x3B', b'\xF0\x3B'), # 'J'
  0x0E: (b'\x42', b'\xF0\x42'), # 'K'
  0x0F: (b'\x4B', b'\xF0\x4B'), # 'L'
  0x10: (b'\x3A', b'\xF0\x3A'), # 'M'
  0x11: (b'\x31', b'\xF0\x31'), # 'N'
  0x12: (b'\x44', b'\xF0\x44'), # 'O'
  0x13: (b'\x4D', b'\xF0\x4D'), # 'P'
  0x14: (b'\x15', b'\xF0\x15'), # 'Q'
  0x15: (b'\x2D', b'\xF0\x2D'), # 'R'
  0x16: (b'\x1B', b'\xF0\x1B'), # 'S'
  0x17: (b'\x2C', b'\xF0\x2C'), # 'T'
  0x18: (b'\x3C', b'\xF0\x3C'), # 'U'
  0x19: (b'\x2A', b'\xF0\x2A'), # 'V'
  0x1A: (b'\x1D', b'\xF0\x1D'), # 'W'
  0x1B: (b'\x22', b'\xF0\x22'), # 'X'
  0x1C: (b'\x35', b'\xF0\x35'), # 'Y'
  0x1D: (b'\x1A', b'\xF0\x1A'), # 'Z'

  0x1E: (b'\x16', b'\xF0\x16'), # '1'
  0x1F: (b'\x1E', b'\xF0\x1E'), # '2'
  0x20: (b'\x26', b'\xF0\x26'), # '3'
  0x21: (b'\x25', b'\xF0\x25'), # '4'
  0x22: (b'\x2E', b'\xF0\x2E'), # '5'
  0x23: (b'\x36', b'\xF0\x36'), # '6'
  0x24: (b'\x3D', b'\xF0\x3D'), # '7'
  0x25: (b'\x3E', b'\xF0\x3E'), # '8'
  0x26: (b'\x46', b'\xF0\x46'), # '9'
  0x27: (b'\x45', b'\xF0\x45'), # '0'
  0x28: (b'\x5A', b'\xF0\x5A'), # '<Return>'
  0x29: (b'\x76', b'\xF0\x76'), # '<Esc>'
  0x2A: (b'\x66', b'\xF0\x66'), # '<Backspace>'
  0x2B: (b'\x0D', b'\xF0\x0D'), # '<Tab>'
  0x2C: (b'\x29', b'\xF0\x29'), # '<Space>'
  0x2D: (b'\x4E', b'\xF0\x4E'), # '-'
  0x2E: (b'\x55', b'\xF0\x55'), # '='
  0x2F: (b'\x54', b'\xF0\x54'), # '['
  0x30: (b'\x5B', b'\xF0\x5B'), # ']'
  0x31: (b'\x5D', b'\xF0\x5D'), # '\'
  0x32: (b'\x5D', b'\xF0\x5D'), #
  0x33: (b'\x4C', b'\xF0\x4C'), # ';'
  0x34: (b'\x52', b'\xF0\x52'), # '\''
  0x35: (b'\x0E', b'\xF0\x0E'), # '`'
  0x36: (b'\x41', b'\xF0\x41'), # ','
  0x37: (b'\x49', b'\xF0\x49'), # '.'
  0x38: (b'\x4a', b'\xF0\x4a'), # '/'
  0x39: (b'\x58', b'\xF0\x58'), # '<CapsLock>'
  0x3a: (b'\x05', b'\xF0\x05'), # '<F1>'
  0x3b: (b'\x06', b'\xF0\x06'), # '<F2>'
  0x3c: (b'\x04', b'\xF0\x04'), # '<F3>'
  0x3d: (b'\x0c', b'\xF0\x0c'), # '<F4>'
  0x3e: (b'\x03', b'\xF0\x03'), # '<F5>'
  0x3f: (b'\x0b', b'\xF0\x0b'), # '<F6>'
  0x40: (b'\x83', b'\xF0\x83'), # '<F7>'
  0x41: (b'\x0a', b'\xF0\x0a'), # '<F8>'
  0x42: (b'\x01', b'\xF0\x01'), # '<F9>'
  0x43: (b'\x09', b'\xF0\x09'), # '<F10>'
  0x44: (b'\x78', b'\xF0\x78'), # '<F11>'
  0x45: (b'\x07', b'\xF0\x07'), # '<F12>'

  0x4f: (b'\xE0\x74', b'\xE0\xF0\x74'), # '<Right>'
  0x50: (b'\xE0\x6B', b'\xE0\xF0\x6B'), # '<Left>'
  0x51: (b'\xE0\x72', b'\xE0\xF0\x72'), # '<Down>'
  0x52: (b'\xE0\x75', b'\xE0\xF0\x75'), # '<Up>'

  0xE0: (b'\x14', b'\xF0\x14'), # '<LCtrl>'
  0xE1: (b'\x12', b'\xF0\x12'), # '<LShift>'
  0xE2: (b'\x11', b'\xF0\x11'), # '<LAlt>'
  0xE3: (b'\xE0\x1F', b'\xE0\xF0\x1F'), # '<LGui>'
  0xE4: (b'\xE0\x14', b'\xE0\xF0\x14'), # '<RCtrl>'
  0xE5: (b'\x59', b'\xF0\x59'), # '<RShift>'
  0xE6: (b'\xE0\x11', b'\xE0\xF0\x11'), # '<RAlt>'
  0xE7: (b'\xE0\x27', b'\xE0\xF0\x27'), # '<RGui>'
}

_scancodeTranslators = (None, _usbToScancodeSet2, None)

class PS2Keyboard(PS2Device):
  def __init__(self):
    self.notifyFunc = None
    self.reset()
  
  def reset(self, includeAck=False):
    self._ledState      = 7
    self._scancodeSetNo = 1
    self._state         = PS2_KEYBOARD_STATE__NORMAL
    if includeAck:
      self._outputBuf = [0xFA,0xAA]
    else:
      self._outputBuf = [0xAA]

    self._notify()

  def poll(self):
    return len(self._outputBuf) > 0

  def read(self):
    if len(self._outputBuf) > 0:
      v = self._outputBuf[0]
      self._outputBuf = self._outputBuf[1:]
      return v

    return None

  def write(self, v):
    if self._state == PS2_KEYBOARD_STATE__NORMAL:
      if v == 0xED: # Update LEDs
        self._queueOutputByte(0xFA)
        self._state = PS2_KEYBOARD_STATE__SET_LED
      elif v == 0xF2: # Read keyboard ID
        self._queueOutputByte(0xFA)
      elif v == 0xF4: # Enable scanning
        self._queueOutputByte(0xFA)
      elif v == 0xF0: # Select scancode
        self._queueOutputByte(0xFA)
        self._state = PS2_KEYBOARD_STATE__SET_SCANCODE
      elif v == 0xF3: # Set repeat rate and delay
        self._queueOutputByte(0xFA)
        self._state = PS2_KEYBOARD_STATE__SET_REPEAT
      elif v == 0xF6: # Reset keyboard, clear output buffer, switch off LEDs, reset repeat rate and delay to defaults
        self._ledState = 0
        self._queueOutputByte(0xFA)
      elif v == 0xFF: # Reset and self test
        self.reset(True)
      else:
        print('@PS2: Keyboard: unknown command: 0x%x' % v)
    elif self._state == PS2_KEYBOARD_STATE__SET_SCANCODE:
      self._selectScancodeSet(v)
      self._queueOutputByte(0xFA)
      self._state = PS2_KEYBOARD_STATE__NORMAL
    elif self._state == PS2_KEYBOARD_STATE__SET_REPEAT:
      print('@PS2: Keyboard: setting repeat 0x%x' % v)
      self._queueOutputByte(0xFA)
      self._state = PS2_KEYBOARD_STATE__NORMAL
    elif self._state == PS2_KEYBOARD_STATE__SET_LED:
      print('@PS2: Keyboard: setting LED state: 0x%x' % v)
      self._ledState = v
      self._queueOutputByte(0xFA)
      self._state = PS2_KEYBOARD_STATE__NORMAL
    else:
      assert False

  # Queues a key down event to be reported to the host, as though typed on this keyboard.
  # x: a USB scancode.
  # (x: int) → ()
  def keyDown(self, x):
    sc = self._toScancode(x)
    if sc is None:
      return

    makeCode, breakCode = sc
    return self._queueCode(makeCode)

  # Queues a key up event to be reported to the host, as though typed on this keyboard.
  # x: a USB scancode.
  # (x: int) → ()
  def keyUp(self, x):
    sc = self._toScancode(x)
    if sc is None:
      return

    makeCode, breakCode = sc
    return self._queueCode(breakCode)

  def _selectScancodeSet(self, scancodeSetNo):
    if scancodeSetNo < 1 or scancodeSetNo > 3:
      scancodeSetNo = 2

    self._scancodeSetNo = scancodeSetNo
    print('@PS2: Keyboard: selecting scancode set no. %s' % scancodeSetNo)

  def _toScancode(self, v):
    sct = _scancodeTranslators[self._scancodeSetNo-1]
    if sct is None:
      print('@PS2: Keyboard: scancode set %s is not supported' % (self._scancodeSetNo))
      return None

    sc = sct.get(v)
    if sc is None:
      print('@PS2: Keyboard: warning: unmappable USB keycode: 0x%x' % v)

    return sc

  def _queueCode(self, code):
    for b in code:
      self._outputBuf.append(b)

    self._notify()

  def _queueOutputByte(self, b):
    self._outputBuf.append(b)
    self._notify()

  def _notify(self):
    if self.notifyFunc:
      self.notifyFunc()

PS2_CTL_STATE__NORMAL         = 0
PS2_CTL_STATE__CFG_RAM_WRITE  = 2

_ps2TranslationTable = [
  0xFF, 0x43, 0x41, 0x3F, 0x3D, 0x3B, 0x3C, 0x58, 0x64, 0x44, 0x42, 0x40, 0x3E, 0x0F, 0x29, 0x59,
  0x65, 0x38, 0x2A, 0x70, 0x1D, 0x10, 0x02, 0x5A, 0x66, 0x71, 0x2C, 0x1F, 0x1E, 0x11, 0x03, 0x5B,
  0x67, 0x2E, 0x2D, 0x20, 0x12, 0x05, 0x04, 0x5C, 0x68, 0x39, 0x2F, 0x21, 0x14, 0x13, 0x06, 0x5D,
  0x69, 0x31, 0x30, 0x23, 0x22, 0x15, 0x07, 0x5e, 0x6a, 0x72, 0x32, 0x24, 0x16, 0x08, 0x09, 0x5f,
  0x6b, 0x33, 0x25, 0x17, 0x18, 0x0b, 0x0a, 0x60, 0x6c, 0x34, 0x35, 0x26, 0x27, 0x19, 0x0c, 0x61,
  0x6d, 0x73, 0x28, 0x74, 0x1a, 0x0d, 0x62, 0x6e, 0x3a, 0x36, 0x1c, 0x1b, 0x75, 0x2b, 0x63, 0x76,
  0x55, 0x56, 0x77, 0x78, 0x79, 0x7a, 0x0e, 0x7b, 0x7c, 0x4f, 0x7d, 0x4b, 0x47, 0x7e, 0x7f, 0x6f,
  0x52, 0x53, 0x50, 0x4c, 0x4d, 0x48, 0x01, 0x45, 0x57, 0x4e, 0x51, 0x4a, 0x37, 0x49, 0x46, 0x54,
  0x80, 0x81, 0x82, 0x41, 0x54, 0x85, 0x86, 0x87, 0x88, 0x89, 0x8a, 0x8b, 0x8c, 0x8d, 0x8e, 0x8f,
  0x90, 0x91, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9a, 0x9b, 0x9c, 0x9d, 0x9e, 0x9f,
  0xa0, 0xa1, 0xa2, 0xa3, 0xa4, 0xa5, 0xa6, 0xa7, 0xa8, 0xa9, 0xaa, 0xab, 0xac, 0xad, 0xae, 0xaf,
  0xb0, 0xb1, 0xb2, 0xb3, 0xb4, 0xb5, 0xb6, 0xb7, 0xb8, 0xb9, 0xba, 0xbb, 0xbc, 0xbd, 0xbe, 0xbf,
  0xc0, 0xc1, 0xc2, 0xc3, 0xc4, 0xc5, 0xc6, 0xc7, 0xc8, 0xc9, 0xca, 0xcb, 0xcc, 0xcd, 0xce, 0xcf,
  0xd0, 0xd1, 0xd2, 0xd3, 0xd4, 0xd5, 0xd6, 0xd7, 0xd8, 0xd9, 0xda, 0xdb, 0xdc, 0xdd, 0xde, 0xdf,
  0xe0, 0xe1, 0xe2, 0xe3, 0xe4, 0xe5, 0xe6, 0xe7, 0xe8, 0xe9, 0xea, 0xeb, 0xec, 0xee, 0xee, 0xef,
  None, 0xf1, 0xf2, 0xf3, 0xf4, 0xf5, 0xf6, 0xf7, 0xf8, 0xf9, 0xfa, 0xfb, 0xfc, 0xff, 0xfe, 0xff,
]

@registerDevice()
class PS2Io(MemoryHandler):
  base = 0x60
  len  = 8

  r60 = Register8(0)
  r61 = Register8(1)
  r64 = Register8(4)

  def __init__(self, vm, sysResetFunc=None):
    self._vm                    = vm
    self._inputBuf              = []
    self._ctlCfgRam             = [0x00]*32
    self._ctlState              = PS2_CTL_STATE__NORMAL
    self._ctlCfgRamOffset       = 0
    self._device                = PS2Keyboard()
    self._device.notifyFunc     = self._onNotify
    self._lastIntrStatus        = False
    self.sysResetFunc           = sysResetFunc

  @property
  def keyboard(self):
    return self._device

  # Data Register
  @r60.getter
  def _(self):
    if self._ctlState == PS2_CTL_STATE__NORMAL:
      if len(self._inputBuf) > 0:
        v = self._inputBuf[0]
        self._inputBuf = self._inputBuf[1:]
        #print('@PS2: Data get cmd response 0x%x' % v)
        self._updateIntr()
        return v

      v = self._device.read()
      self._updateIntr()
      if v is None:
        print('@PS2: No data')
        return 0

      oldv = v
      v = self._translate(v)
      if v is None:
        v = self._translate(self._device.read())
        self._updateIntr()
        assert v is not None
        v = v | 0x80

      #print('@PS2: Data get device input 0x%x' % v)
      return v
    else:
      print('@PS2: Warning: unexpected state when reading from data port')
      self._ctlState = PS2_CTL_STATE__NORMAL
      return 0

  @r60.setter
  def _(self, v):
    if self._ctlState == PS2_CTL_STATE__NORMAL:
      #print('@PS2: To keyboard: 0x%x' % v)
      self._device.write(v)
    elif self._ctlState == PS2_CTL_STATE__CFG_RAM_WRITE:
      #print('@PS2: ram set [0x%x] = 0x%x' % (self._ctlCfgRamOffset, v))
      self._ctlCfgRam[self._ctlCfgRamOffset] = v
      self._updateIntr()
      self._ctlState = PS2_CTL_STATE__NORMAL
    else:
      print('@PS2: Warning: unexpected state when writing to data port: 0x%x' % v)
      self._ctlState = PS2_CTL_STATE__NORMAL

  # Status Register
  @r64.getter
  def _(self):
    flags = 0 
    if len(self._inputBuf) != 0 or self._device.poll():
      flags = flags | (1<<0) # At least one byte in Keyboard to Host buffer
    if self._ctlCfgRam[0] & (1<<2):
      flags = flags | (1<<2) # System Flag
    if self._ctlState == PS2_CTL_STATE__CFG_RAM_WRITE:
      flags = flags | (1<<3) # Command?
    #flags = flags | (1<<1) # Host to Keyboard buffer full
    return flags

  # Command Register
  @r64.setter
  def _(self, v):
    if v >= 0x20 and v <= 0x3F:
      offset = v & 0x1F
      self._inputBuf.append(self._ctlCfgRam[offset])
    elif v >= 0x60 and v <= 0x7F:
      offset = v & 0x1F
      self._ctlState = PS2_CTL_STATE__CFG_RAM_WRITE
      self._ctlCfgRamOffset = offset
    elif v == 0xAD: # Disable PS/2 port A (keyboard)
      self._ctlCfgRam[0] |= (1<<4)
    elif v == 0xAE: # Enable PS/2 port A (keyboard)
      self._ctlCfgRam[0] &= ~(1<<4)
    elif v == 0xA7: # Disable PS/2 port B (mouse)
      self._ctlCfgRam[0] |= (1<<5)
    elif v == 0xA8: # Enable PS/2 port B (mouse)
      self._ctlCfgRam[0] &= ~(1<<5)
    elif v == 0xAA: # Test PS/2 Controller
      self._inputBuf.append(0x55)
    elif v == 0xAB: # Test PS/2 port A (keyboard)
      self._inputBuf.append(0x00)
    elif v == 0xA9: # Test PS/2 port B (mouse)
      self._inputBuf.append(0x06)
    elif v & 0xF0 == 0xF0:
      # Pulse output lines low for 6ms
      doReset = False
      for i in range(4):
        if (v & (1<<i)) == 0:
          if i == 0:
            doReset = True
          else:
            print('@PS2: Warning: pulsing unknown line %s' % i)

      if doReset:
        print('@PS2: System reset via keyboard controller')
        if self.sysResetFunc:
          self.sysResetFunc()

    else:
      print('@PS2: Warning: Unknown command 0x%x' % v)

  def _translate(self, v):
    if (self._ctlCfgRam[0] & (1<<6)) == 0:
      return v

    if v == 0xF0:
      return None

    return _ps2TranslationTable[v]

  @r61.getter # GRUB2 compat (GRUB_PIT_SPEAKER_PORT)
  def _(self):
    print('WARNING: get r61')
    return 0x21

  @r61.setter
  def _(self, v):
    print('WARNING: set r61: 0x%x' % v)

  def _onNotify(self):
    self._updateIntr()

  def _updateIntr(self):
    newIntrStatus = bool(self._ctlCfgRam[0] & 1) and (len(self._inputBuf) > 0 or self._device.poll())
    #if self._lastIntrStatus != newIntrStatus:
    self._lastIntrStatus = newIntrStatus
    self._vm.setIrqLine(1, False)
    if newIntrStatus:
      self._vm.setIrqLine(1, newIntrStatus)
