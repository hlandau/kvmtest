# From https://github.com/flababah/cpuid.py/blob/master/cpuid.py
import os, ctypes

class CPUID(ctypes.Structure):
  _fields_ = [
    ('eax', ctypes.c_uint32),
    ('ebx', ctypes.c_uint32),
    ('ecx', ctypes.c_uint32),
    ('edx', ctypes.c_uint32)
  ]

def get_cpuid():
  _POSIX_64_OPC = [
    0x53,             # push  %rbx
    0x89, 0xf0,       # mov   %esi, %eax
    0x89, 0xd1,       # mov   %edx, %ecx
    0x0f, 0xa2,       # cpuid
    0x89, 0x07,       # mov   %eax,    (%rdi)
    0x89, 0x5f, 0x04, # mov   %ebx, 0x4(%rdi)
    0x89, 0x4f, 0x08, # mov   %ecx, 0x8(%rdi)
    0x89, 0x57, 0x0c, # mov   %edx, 0xC(%rdi)
    0x5b,             # pop   %rbx
    0xc3,             # retq
  ]

  code = (ctypes.c_ubyte*len(_POSIX_64_OPC))(*_POSIX_64_OPC)

  _libc = ctypes.cdll.LoadLibrary(None)
  _libc.valloc.restype = ctypes.c_void_p
  _libc.valloc.argtypes = [ctypes.c_size_t]
  addr = _libc.valloc(len(_POSIX_64_OPC))
  if not addr:
    raise Exception("allocation failure")

  _libc.mprotect.restype = ctypes.c_int
  _libc.mprotect.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int]
  ret = _libc.mprotect(addr, len(_POSIX_64_OPC), 1|2|4)
  if ret:
    raise Exception("mprotect failure")

  ctypes.memmove(addr, code, len(_POSIX_64_OPC))

  func_type = ctypes.CFUNCTYPE(None, ctypes.POINTER(CPUID), ctypes.c_uint32, ctypes.c_uint32)
  f = func_type(addr)
  def g(eax, ecx):
    s = CPUID()
    f(s, eax, ecx)
    return s

  return g

get_cpuid = get_cpuid()
