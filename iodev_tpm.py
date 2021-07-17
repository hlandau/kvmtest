from iodev import *

class TpmTis(MemoryHandler):
  base = 0xFED4_0000
  len  = 0x0001_0000

  def read8(self, addr):
    return 0xFF
