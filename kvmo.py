import kvmapi, os, fcntl, mmap, errno, struct, ctypes

class Kvm:
  def __init__(self):
    self._fd = os.open('/dev/kvm', os.O_RDWR | os.O_CLOEXEC)

    kernApiVer = fcntl.ioctl(self._fd, kvmapi.KVM_GET_API_VERSION)
    if kernApiVer != kvmapi.KVM_API_VERSION:
      raise Exception(f"unexpected API version: kernel uses API version {kernApiVer}, expected version {kvmapi.KVM_API_VERSION}")

    self._mapLen = fcntl.ioctl(self._fd, kvmapi.KVM_GET_VCPU_MMAP_SIZE)

  def createVM(self):
    return VM(self)

  def checkExtension(self, ext):
    return bool(fcntl.ioctl(self._fd, kvmapi.KVM_CHECK_EXTENSION, int(ext)) >= 0)

  def getSupportedCpuid(self):
    n = 128
    while True:
      try:
        info = kvmapi.makeKvmCpuid2(n)()
        info.nent = n
        fcntl.ioctl(self._fd, kvmapi.KVM_GET_SUPPORTED_CPUID, info)
        return info.entries[0:info.nent]
      except OSError as e:
        if e.errno == errno.E2BIG:
          n = 2*n
          continue
        else:
          raise

  def getMsrs(self, msrNumList):
    msrs = kvmapi.makeKvmMsrs(len(msrNumList))()
    msrs.nmsrs = len(msrNumList)
    for i, x in enumerate(msrNumList):
      msrs.entries[i].index = x
      msrs.entries[i].data  = 0x55555555

    L = fcntl.ioctl(self._fd, kvmapi.KVM_GET_MSRS, msrs)
    return msrs.entries[0:L]

  def _getMsrIndexList(self, op):
    L = 1
    while True:
      msrList       = kvmapi.makeKvmMsrList(L)()
      msrList.nmsrs = L
      try:
        fcntl.ioctl(self._fd, op, msrList)
        return msrList.indices[0:msrList.nmsrs]
      except OSError as e:
        if e.errno == errno.E2BIG:
          L = msrList.nmsrs
          continue
        else:
          raise

  def getMsrIndexList(self):
    return self._getMsrIndexList(kvmapi.KVM_GET_MSR_INDEX_LIST)

  def getMsrFeatureIndexList(self):
    return self._getMsrIndexList(kvmapi.KVM_GET_MSR_FEATURE_INDEX_LIST)

  @property
  def fd(self):
    return self._fd

class VM:
  def __init__(self, kvm):
    assert isinstance(kvm, Kvm)

    self._kvm = kvm
    self._fd = fcntl.ioctl(self._kvm._fd, kvmapi.KVM_CREATE_VM, 0)

  def createVcpu(self, *args, **kwargs):
    return Vcpu(self, *args, **kwargs)

  def setUserMemoryRegion(self, rgn):
    assert isinstance(rgn, kvmapi.KvmUserSpaceMemoryRegion)
    fcntl.ioctl(self._fd, kvmapi.KVM_SET_USER_MEMORY_REGION, rgn)

  def setTssAddr(self, addr):
    addr = struct.unpack('i', struct.pack('I', addr))[0]
    fcntl.ioctl(self._fd, kvmapi.KVM_SET_TSS_ADDR, addr)

  def createPit2(self, cfg):
    assert isinstance(cfg, kvmapi.KvmPitConfig)
    fcntl.ioctl(self._fd, kvmapi.KVM_CREATE_PIT2, cfg)

  def createIrqChip(self):
    fcntl.ioctl(self._fd, kvmapi.KVM_CREATE_IRQCHIP)

  def setIrqLine(self, irq, level):
    args = kvmapi.KvmIrqLevel(irq, int(level))
    fcntl.ioctl(self._fd, kvmapi.KVM_IRQ_LINE, args)

  @property
  def kvm(self):
    return self._kvm

  @property
  def fd(self):
    return self._fd

class Vcpu:
  def __init__(self, vm, cpuNum=0):
    assert isinstance(vm, VM)
    self._vm = vm
    self._fd = fcntl.ioctl(self._vm._fd, kvmapi.KVM_CREATE_VCPU, cpuNum)
    self._runBase = kvmapi.mmap(-1, self._vm._kvm._mapLen, mmap.PROT_READ | mmap.PROT_WRITE, mmap.MAP_SHARED, self._fd, 0)
    self._run = kvmapi.KvmRun.from_address(self._runBase)
    self._runBuf = (ctypes.c_uint8 * self._vm._kvm._mapLen).from_address(self._runBase)
    #self._runBase = mmap.mmap(self._fd, self._vm._kvm._mapLen)
    #self._run = kvmapi.KvmRun.from_buffer(self._runBase)

  def teardown(self):
    self._run    = None
    self._runBuf = None
    kvmapi.munmap(self._runBase, self._vm._kvm._mapLen)
    #self._runBase.close()
    os.close(self._fd)

  @property
  def regs(self):
    regs = kvmapi.KvmRegs()
    fcntl.ioctl(self._fd, kvmapi.KVM_GET_REGS, regs)
    return regs

  @regs.setter
  def regs(self, regs):
    assert isinstance(regs, kvmapi.KvmRegs)
    fcntl.ioctl(self._fd, kvmapi.KVM_SET_REGS, regs)

  @property
  def sregs(self):
    sregs = kvmapi.KvmSregs()
    fcntl.ioctl(self._fd, kvmapi.KVM_GET_SREGS, sregs)
    return sregs

  @sregs.setter
  def sregs(self, sregs):
    assert isinstance(sregs, kvmapi.KvmSregs)
    fcntl.ioctl(self._fd, kvmapi.KVM_SET_SREGS, sregs)

  @property
  def fpu(self):
    fpu = kvmapi.KvmFpu()
    fcntl.ioctl(self._fd, kvmapi.KVM_GET_FPU, fpu)
    return fpu

  @fpu.setter
  def fpu(self, fpu):
    assert isinstance(fpu, kvmapi.KvmFpu)
    fcntl.ioctl(self._fd, kvmapi.KVM_SET_FPU, fpu)

  @property
  def lapic(self):
    lapic = kvmapi.LocalApic()
    fcntl.ioctl(self._fd, kvmapi.KVM_GET_LAPIC, lapic)
    return lapic

  @lapic.setter
  def lapic(self, lapic):
    assert isinstance(lapic, kvmapi.LocalApic)
    fcntl.ioctl(self._fd, kvmapi.KVM_SET_LAPIC, lapic)

  def setCpuid2(self, cpuid):
    if isinstance(cpuid, list):
      cpuid2 = kvmapi.makeKvmCpuid2(len(cpuid))()
      cpuid2.nent = len(cpuid)
      for i in range(len(cpuid)):
        cpuid2.entries[i] = cpuid[i]
      cpuid = cpuid2

    assert isinstance(cpuid.entries[0], kvmapi.KvmCpuidEntry2)
    fcntl.ioctl(self._fd, kvmapi.KVM_SET_CPUID2, cpuid)

  def getMsrs(self, msrNumList):
    msrs = kvmapi.makeKvmMsrs(len(msrNumList))()
    msrs.nmsrs = len(msrNumList)
    for i, x in enumerate(msrNumList):
      msrs.entries[i].index = x
      msrs.entries[i].data  = 0x55555555

    L = fcntl.ioctl(self._fd, kvmapi.KVM_GET_MSRS, msrs)
    return msrs.entries[0:L]

  def setMsrs(self, msrs):
    if isinstance(msrs, list):
      msrs2 = kvmapi.makeKvmMsrs(len(msrs))()
      msrs2.nmsrs = len(msrs)
      for i in range(len(msrs)):
        msrs2.entries[i] = msrs[i]
      msrs = msrs2

    assert isinstance(msrs.entries[0], kvmapi.KvmMsrEntry)
    fcntl.ioctl(self._fd, kvmapi.KVM_SET_MSRS, msrs)

  def setDebug(self, debugs):
    assert isinstance(debugs, kvmapi.KvmGuestDebug)
    fcntl.ioctl(self._fd, kvmapi.KVM_SET_GUEST_DEBUG, debugs)

  def runOnce(self):
    fcntl.ioctl(self._fd, kvmapi.KVM_RUN, 0)

  @property
  def reason(self):
    return kvmapi.KvmExitReason(self._run.exitReason)

  @property
  def runData(self):
    return self._run

  @property
  def runBase(self):
    return self._runBase

  @property
  def runBuf(self):
    return self._runBuf

  @property
  def vm(self):
    return self._vm

  @property
  def fd(self):
    return self._fd
