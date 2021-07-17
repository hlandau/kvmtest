from iodev import *

@registerDevice()
class IoAcpiTmr(MemoryHandler):
  base = 0x608
  len  = 4
  _v   = 0

  r = Register32(0, ro=True)

  @r.getter
  def _(self):
    self._v += 1000
    return self._v

@registerDevice()
class IoAcpiCnt(MemoryHandler):
  base = 0x604
  len  = 4

  r    = Register16(0)

  @r.getter
  def _(self):
    print('ACPI-CNT get')
    return 0

  @r.setter
  def _(self, v):
    print('ACPI-CNT set 0x%x' % v)

class Q35PmIo(AddressSpace):
  base = 0x600
  len  = 0x80

  def __init__(self):
    super().__init__()
    self.ioAcpiCnt = self.mount(IoAcpiCnt())
    self.ioAcpiTmr = self.mount(IoAcpiTmr())
