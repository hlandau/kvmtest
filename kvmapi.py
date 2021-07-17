import ctypes, ctypes.util, enum
from ioctl_opt import IO, IOR, IOW, IOWR
from ctypes import c_uint8, c_uint16, c_uint32, c_uint64, c_char_p

libc = ctypes.cdll.LoadLibrary(ctypes.util.find_library('c'))
libc.mmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int, ctypes.c_int, ctypes.c_size_t]
libc.mmap.restype = ctypes.c_void_p
libc.munmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
libc.munmap.restype = ctypes.c_int

mmap = libc.mmap
munmap = libc.munmap

class KvmUserSpaceMemoryRegion(ctypes.Structure):
  _fields_ = [
    ('slot', c_uint32),
    ('flags', c_uint32),
    ('guestPhysAddr', c_uint64),
    ('memSize', c_uint64),
    ('userspaceAddr', c_uint64),
  ]

KVM_MEM_READONLY = (1<<1)

class KvmRegs(ctypes.Structure):
  _fields_ = [
    ('rax', c_uint64),
    ('rbx', c_uint64),
    ('rcx', c_uint64),
    ('rdx', c_uint64),
    ('rsi', c_uint64),
    ('rdi', c_uint64),
    ('rsp', c_uint64),
    ('rbp', c_uint64),
    ('r8', c_uint64),
    ('r9', c_uint64),
    ('r10', c_uint64),
    ('r11', c_uint64),
    ('r12', c_uint64),
    ('r13', c_uint64),
    ('r14', c_uint64),
    ('r15', c_uint64),
    ('rip', c_uint64),
    ('rflags', c_uint64),
  ]

class KvmSegment(ctypes.Structure):
  _fields_ = [
    ('base', c_uint64),
    ('limit', c_uint32),
    ('selector', c_uint16),
    ('type', c_uint8),
    ('present', c_uint8),
    ('dpl', c_uint8),
    ('db', c_uint8),
    ('s', c_uint8),
    ('l', c_uint8),
    ('g', c_uint8),
    ('avl', c_uint8),
    ('unusable', c_uint8),
    ('padding', c_uint8),
  ]

class KvmDtable(ctypes.Structure):
  _fields_ = [
    ('base', c_uint64),
    ('limit', c_uint16),
    ('padding', c_uint16*3),
  ]

KVM_NUM_INTR = 256

class KvmSregs(ctypes.Structure):
  _fields_ = [
    ('cs', KvmSegment),
    ('ds', KvmSegment),
    ('es', KvmSegment),
    ('fs', KvmSegment),
    ('gs', KvmSegment),
    ('ss', KvmSegment),
    ('tr', KvmSegment),
    ('ldt', KvmSegment),
    ('gdt', KvmDtable),
    ('idt', KvmDtable),
    ('cr0', c_uint64),
    ('cr2', c_uint64),
    ('cr3', c_uint64),
    ('cr4', c_uint64),
    ('cr8', c_uint64),
    ('efer', c_uint64),
    ('apicBase', c_uint64),
    ('intrBitmap', c_uint64*((KVM_NUM_INTR+63)//64)),
  ]

class KvmFpu(ctypes.Structure):
  _fields_ = [
    ('fpu', c_uint8*8*16),
    ('fcw', c_uint16),
    ('fsw', c_uint16),
    ('ftwx', c_uint8),
    ('pad1', c_uint8),
    ('lastOpcode', c_uint16),
    ('lastIP', c_uint64),
    ('lastDP', c_uint64),
    ('xmm', c_uint8*16*16),
    ('mxcsr', c_uint32),
    ('pad2', c_uint32),
  ]

class KvmExitReason(enum.IntEnum):
  KVM_EXIT_UNKNOWN = 0
  KVM_EXIT_EXCEPTION = 1
  KVM_EXIT_IO = 2
  KVM_EXIT_HYPERCALL = 3
  KVM_EXIT_DEBUG = 4
  KVM_EXIT_HLT = 5
  KVM_EXIT_MMIO = 6
  KVM_EXIT_IRQ_WINDOW_OPEN = 7
  KVM_EXIT_SHUTDOWN = 8
  KVM_EXIT_FAIL_ENTRY = 9
  KVM_EXIT_INTR = 10
  KVM_EXIT_SET_TPR = 11
  KVM_EXIT_TPR_ACCESS = 12
  KVM_EXIT_DCR = 15
  KVM_EXIT_NMI = 16
  KVM_EXIT_INTERNAL_ERROR = 17
  KVM_EXIT_OSI = 18
  KVM_EXIT_WATCHDOG = 21
  KVM_EXIT_EPR = 23
  KVM_EXIT_SYSTEM_EVENT = 24

class KvmRunExitMmio(ctypes.Structure):
  _fields_ = [
    ('physAddr', c_uint64),
    ('data', c_uint8*8),
    ('len', c_uint32),
    ('isWrite', c_uint8),
  ]

class KvmRunExitIO(ctypes.Structure):
  _fields_ = [
    ('direction', c_uint8),
    ('size', c_uint8),
    ('port', c_uint16),
    ('count', c_uint32),
    ('dataOffset', c_uint64),
  ]

class KvmRunExitInternal(ctypes.Structure):
  _fields_ = [
    ('suberror', c_uint32),
    ('ndata', c_uint32),
    ('data', c_uint64*16),
  ]

class KvmRunExitUnknown(ctypes.Structure):
  _fields_ = [
    ('hardwareExitReason', c_uint64),
  ]

class KvmRunExitDebug(ctypes.Structure):
  _fields_ = [
    ('exception', c_uint32),
    ('pad', c_uint32),
    ('pc', c_uint64),
    ('dr6', c_uint64),
    ('dr7', c_uint64),
  ]

class KvmRunExitReasons(ctypes.Union):
  _fields_ = [
    ('hw', KvmRunExitUnknown),
    ('debug', KvmRunExitDebug),
    ('internal', KvmRunExitInternal),
    ('io', KvmRunExitIO),
    ('mmio', KvmRunExitMmio),
  ]

class KvmRun(ctypes.Structure):
  _fields_ = [
    ('requestIntrWindow', c_uint8),
    ('padding1', c_uint8*7),
    ('exitReason', c_uint32),
    ('readyForIntrInjection', c_uint8),
    ('ifFlag', c_uint8),
    ('padding2', c_uint8*2),
    ('cr8', c_uint64),
    ('apicBase', c_uint64),
    ('exitReasons', KvmRunExitReasons),
  ]

class KvmCpuidEntry2(ctypes.Structure):
  _fields_ = [
    ('function', c_uint32),
    ('index', c_uint32),
    ('flags', c_uint32),
    ('eax', c_uint32),
    ('ebx', c_uint32),
    ('ecx', c_uint32),
    ('edx', c_uint32),
    ('padding', c_uint32*3),
  ]

  def __repr__(self):
    return "CPUID(func=0x%x, idx=0x%x, flags=0x%x, EAX=0x%x, EBX=0x%x, ECX=0x%x, EDX=0x%x)" % (self.function, self.index, self.flags, self.eax, self.ebx, self.ecx, self.edx)

_kvmCpuid2 = {}
def makeKvmCpuid2(n):
  if n in _kvmCpuid2:
    return _kvmCpuid2[n]

  class KvmCpuid2(ctypes.Structure):
    _fields_ = [
      ('nent', c_uint32),
      ('padding1', c_uint32),
      ('entries', KvmCpuidEntry2*n),
    ]

  _kvmCpuid2[n] = KvmCpuid2
  return KvmCpuid2

class KvmMsrEntry(ctypes.Structure):
  _fields_ = [
    ('index',     c_uint32),
    ('reserved',  c_uint32),
    ('data',      c_uint64),
  ]

_kvmMsrs = {}
def makeKvmMsrs(n):
  if n in _kvmMsrs:
    return _kvmMsrs[n]

  class KvmMsrs(ctypes.Structure):
    _fields_ = [
      ('nmsrs', c_uint32),
      ('pad', c_uint32),
      ('entries', KvmMsrEntry*n),
    ]

  _kvmMsrs[n] = KvmMsrs
  return KvmMsrs

_kvmMsrList = {}
def makeKvmMsrList(n):
  if n in _kvmMsrList:
    return _kvmMsrList[n]

  class KvmMsrList(ctypes.Structure):
    _fields_ = [
      ('nmsrs', c_uint32),
      ('indices', c_uint32*n),
    ]

  _kvmMsrList[n] = KvmMsrList
  return KvmMsrList

class KvmPitConfig(ctypes.Structure):
  _fields_ = [
    ('flags', c_uint32),
    ('pad', c_uint32*15),
  ]

KVM_GUESTDBG_ENABLE     = 1
KVM_GUESTDBG_SINGLESTEP = 2

class KvmGuestDebug(ctypes.Structure):
  _fields_ = [
    ('control', c_uint32),
    ('pad', c_uint32),
    ('debugreg', c_uint64*8),
  ]

class KvmCapability(enum.IntEnum):
  KVM_CAP_IRQCHIP             =  0
  KVM_CAP_HLT                 =  1
  KVM_CAP_USER_MEMORY         =  3
  KVM_CAP_SET_TSS_ADDR        =  4
  KVM_CAP_EXT_CPUID           =  7
  KVM_CAP_COALESCED_MMIO      = 15
  KVM_CAP_IRQ_ROUTING         = 25
  KVM_CAP_IRQ_INJECT_STATUS   = 26
  KVM_CAP_PIT2                = 33

KVM_API_VERSION = 12

KVMIO                     = 0xAE

KVM_GET_API_VERSION         = IO(KVMIO, 0x00)
KVM_CREATE_VM               = IO(KVMIO, 0x01)
KVM_CHECK_EXTENSION         = IO(KVMIO, 0x03)
KVM_GET_VCPU_MMAP_SIZE      = IO(KVMIO, 0x04)
KVM_GET_SUPPORTED_CPUID     = 0xC008AE05
KVM_SET_CPUID2              = 0x4008AE90
KVM_GET_FPU                 = IOR(KVMIO, 0x8C, KvmFpu)
KVM_SET_FPU                 = IOW(KVMIO, 0x8D, KvmFpu)
#def KVM_GET_SUPPORTED_CPUID(n):
#  return IOWR(KVMIO, 0x05, ctypes.c_void) #makeKvmCpuid2(100)) # KvmCpuid2
KVM_SET_MSRS                = 0x4008AE89
KVM_GET_MSRS                = 0xC008AE88
KVM_GET_MSR_INDEX_LIST      = 0xC004AE02
KVM_GET_MSR_FEATURE_INDEX_LIST  = 0xC004AE0A

KVM_CREATE_PIT2             = IOW(KVMIO, 0x77, KvmPitConfig)
KVM_CREATE_IRQCHIP          = IO(KVMIO, 0x60)

KVM_CREATE_VCPU             = IO(KVMIO, 0x41)
KVM_SET_TSS_ADDR            = IO(KVMIO, 0x47)
KVM_SET_USER_MEMORY_REGION  = IOW(KVMIO, 0x46, KvmUserSpaceMemoryRegion)

KVM_RUN                     = IO(KVMIO, 0x80)
KVM_GET_REGS                = IOR(KVMIO, 0x81, KvmRegs)
KVM_SET_REGS                = IOW(KVMIO, 0x82, KvmRegs)
KVM_GET_SREGS               = IOR(KVMIO, 0x83, KvmSregs)
KVM_SET_SREGS               = IOW(KVMIO, 0x84, KvmSregs)

KVM_SET_GUEST_DEBUG = IOW(KVMIO, 0x9B, KvmGuestDebug)

class LocalApicIsr(ctypes.Structure):
  _fields_ = [
    ('v', c_uint32),
    ('_reserved', c_uint32*3),
  ]

class LocalApicTmr(ctypes.Structure):
  _fields_ = [
    ('v', c_uint32),
    ('_reserved', c_uint32*3),
  ]

class LocalApicIrr(ctypes.Structure):
  _fields_ = [
    ('v', c_uint32),
    ('_reserved', c_uint32*3),
  ]

class LocalApic(ctypes.Structure):
  _fields_ = [
    ('_reserved', c_uint32*8),
    ('id', c_uint32),
    ('_reserved2', c_uint32*3),
    ('version', c_uint32),
    ('_reserved3', c_uint32*(3+4+4+4+4)),
    ('tpr', c_uint32),
    ('_reserved4', c_uint32*3),
    ('apr', c_uint32),
    ('_reserved5', c_uint32*3),
    ('ppr', c_uint32),
    ('_reserved6', c_uint32*3),
    ('eoi', c_uint32),
    ('_reserved7', c_uint32*(3+4)),
    ('ldr', c_uint32),
    ('_reserved8', c_uint32*3),
    ('dfr', c_uint32),
    ('_reserved9', c_uint32*3),
    ('svr', c_uint32),
    ('_reserved10', c_uint32*3),
    ('isr', LocalApicIsr*8),
    ('tmr', LocalApicTmr*8),
    ('irr', LocalApicIrr*8),
    ('esr', c_uint32),
    ('_reserved12', c_uint32*(3+4+4+4+4+4+4+4)),
    ('icr1', c_uint32),
    ('_reserved13', c_uint32*3),
    ('icr2', c_uint32),
    ('_reserved14', c_uint32*3),
    ('lvtTimer', c_uint32),
    ('_reserved15', c_uint32*3),
    ('lvtThermal', c_uint32),
    ('_reserved16', c_uint32*3),
    ('lvtPC', c_uint32),
    ('_reserved17', c_uint32*3),
    ('lvtLINT0', c_uint32),
    ('_reserved18', c_uint32*3),
    ('lvtLINT1', c_uint32),
    ('_reserved19', c_uint32*3),
    ('lvtError', c_uint32),
    ('_reserved20', c_uint32*3),
    ('timerIcr', c_uint32),
    ('_reserved21', c_uint32*3),
    ('timerCcr', c_uint32),
    ('_reserved22', c_uint32*(3+4+4+4+4)),
    ('timerDcr', c_uint32),
    ('_reserved23', c_uint32*(3+4)),
  ]

KVM_GET_LAPIC               = IOR(KVMIO, 0x8E, LocalApic)
KVM_SET_LAPIC               = IOW(KVMIO, 0x8F, LocalApic)
assert ctypes.sizeof(LocalApic) == 0x400

class KvmIrqLevel(ctypes.Structure):
  _fields_ = [
    ('irq',   c_uint32),
    ('level', c_uint32),
  ]

KVM_IRQ_LINE = IOW(KVMIO, 0x61, KvmIrqLevel)
