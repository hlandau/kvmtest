import mmap, ctypes, struct
import kvmo, kvmapi
from cpuid import *
from x86 import *
from iodev_qemu import *
from memmgr import *

MAP_NORESERVE = 0x4000

class VMM:
  def __init__(self, platformFunc, firmwarePath, firmwareVarsPath, opticalPath=None, diskPath=None):
    self.kvm = kvmo.Kvm()

    for e in (
        kvmapi.KvmCapability.KVM_CAP_COALESCED_MMIO,
        kvmapi.KvmCapability.KVM_CAP_SET_TSS_ADDR,
        kvmapi.KvmCapability.KVM_CAP_PIT2,
        kvmapi.KvmCapability.KVM_CAP_USER_MEMORY,
        kvmapi.KvmCapability.KVM_CAP_IRQ_ROUTING,
        kvmapi.KvmCapability.KVM_CAP_IRQCHIP,
        kvmapi.KvmCapability.KVM_CAP_HLT,
        kvmapi.KvmCapability.KVM_CAP_IRQ_INJECT_STATUS,
        kvmapi.KvmCapability.KVM_CAP_EXT_CPUID):
      self.kvm.checkExtension(e)

    self.cpuids = self.kvm.getSupportedCpuid()

    self._firmwarePath = firmwarePath
    self._firmwareVarsPath = firmwareVarsPath
    self._initVM()
    self._initVcpu()
    self._resetVcpu()
    self.i = 0
    self._memMgr = MemoryManager(self)
    self._platform = platformFunc(memoryManager=self._memMgr, firmwarePath=self._firmwarePath, firmwareVarsPath=self._firmwareVarsPath, vm=self.vm, sysResetFunc=self.onSysReset, opticalPath=opticalPath, diskPath=diskPath)

  def _initVM(self):
    self.vm = self.kvm.createVM()
    #self.vm.setTssAddr(0xFFFBD000)
    self.vm.createPit2(kvmapi.KvmPitConfig())
    self.vm.createIrqChip()

  def _initVcpu(self):
    self.vcpu = self.vm.createVcpu()
    self._vcpuOrigRegs = self.vcpu.regs
    self._vcpuOrigSregs = self.vcpu.sregs
    self._vcpuOrigFpu = self.vcpu.fpu

    self.virtCpuids = []
    for c in self.cpuids:
      #if c.function == 0:
      #  self.virtCpuids.append(kvmapi.KvmCpuidEntry2(0, 0, 0, c.eax, 0x44444444, 0x44444444, 0x44444444))
      #  #self.virtCpuids.append(kvmapi.KvmCpuidEntry2(0, 0, 0, c.eax, ebx, ecx, edx))
      #  #self.virtCpuids.append(kvmapi.KvmCpuidEntry2(0, 0, 0, c.eax, 0x42413938, 0x37363534, 0x33323130))
      if c.function == 1:
        r = get_cpuid(0x1, 0)
        c.eax = r.eax
        c.ebx = r.ebx
        c.ecx = r.ecx
        c.edx = r.edx
        #c.ecx = 0x37363534
        #c.edx = 0x078bfbff
        #c.ecx |= (1<<31)
        #c.ecx |= (1<<0) | (1<<1) | (1<<9) | (1<<28) | (1<<19) | (1<<20) | (1<<23) # SSE3 PCLMULDQ SSSE3 AVX SSE4.1 SSE4.2 POPCNT
        c.ecx |= (1<<31)
        self.virtCpuids.append(c)
      elif c.function == 2:
        r = get_cpuid(0x2, 0)
        c.eax = r.eax
        c.ebx = r.ebx
        c.ecx = r.ecx
        c.edx = r.edx
        self.virtCpuids.append(c)
      elif c.function == 7:
        r = get_cpuid(0x7, 0)
        c.eax = r.eax
        c.ebx = r.ebx
        c.ecx = r.ecx
        c.edx = r.edx
        self.virtCpuids.append(c)
      elif c.function == 0x80000001:
        r = get_cpuid(0x80000001, 0)
        c.eax = r.eax
        c.ebx = r.ebx
        c.ecx = r.ecx
        c.edx = r.edx
        self.virtCpuids.append(c)
      elif c.function == 0x80000005:
        r = get_cpuid(0x80000005, 0)
        self.virtCpuids.append(kvmapi.KvmCpuidEntry2(0x80000005, 0, 0, r.eax, r.ebx, r.ecx, r.edx))
      elif c.function == 0x80000006:
        r = get_cpuid(0x80000006, 0)
        self.virtCpuids.append(kvmapi.KvmCpuidEntry2(0x80000006, 0, 0, r.eax, r.ebx, r.ecx, r.edx))
      elif c.function == 0x80000008:
        r = get_cpuid(0x80000008, 0)
        self.virtCpuids.append(kvmapi.KvmCpuidEntry2(0x80000008, 0, 0, r.eax, r.ebx, r.ecx, r.edx))
      else:
        self.virtCpuids.append(c)

    cpuid = b'KVMKVMKVM\0\0\0'
    ebx, ecx, edx = struct.unpack('<III', cpuid[0:12])
    self.virtCpuids.append(kvmapi.KvmCpuidEntry2(0x4000_0000, 0, 0, 0x4000_0001 | 0x4000_0000, ebx, ecx, edx))
    #self.virtCpuids.append(kvmapi.KvmCpuidEntry2(0x4000_0001, 0, 0, 0, 0, 0, 0))
    self.vcpu.setCpuid2(self.virtCpuids)
    self._initVcpuLapic(self.vcpu)

    filterMsrs = (MSR_TSC, 0x4000_0020)
    hiddenMsrs = [0x200, 0x201, 0x202, 0x203, 0x204, 0x205, 0x206, 0x207, 0x208, 0x209, 0x20a, 0x20b, 0x20c, 0x20d, 0x20e, 0x20f,
                  0x250, 0x258, 0x259, 0x268, 0x269, 0x26a, 0x26b, 0x26c, 0x26d, 0x26e, 0x26f, 0x277, 0x2ff]
    mil = list(filter(lambda x: x not in filterMsrs, self.kvm.getMsrIndexList())) + hiddenMsrs
    self._initialMsrState = {}
    for e in self.vcpu.getMsrs(mil):
      self._initialMsrState[e.index] = e.data

  def onSysReset(self):
    self._memMgr.clear()
    self._resetVcpu()

  def _resetVcpu(self):
    sregs = self._vcpuOrigSregs
    for x in ('cs','ss','ds','es','fs','gs'):
      q = getattr(sregs,x)
      q.selector = 0xF000
      q.base     = 0xF000<<4
    self.vcpu.sregs = sregs

    regs = kvmapi.KvmRegs()
    regs.rflags = 2
    regs.rip    = 0xFFF0
    regs.rsp    = 0x8000
    regs.rbp    = 0x8000
    self.vcpu.regs = regs

    fpu = kvmapi.KvmFpu()
    fpu.fcw     = 0x37f
    fpu.mxcsr   = 0x1f80
    self.vcpu.fpu = fpu

    msrs = []
    def addMsr(k,v):
      z = kvmapi.KvmMsrEntry()
      z.index = k
      z.data = v
      msrs.append(z)

    initialMsrState   = list(self._initialMsrState.items())
    curMsrValues      = self.vcpu.getMsrs(list([k for k, v in initialMsrState]))
    for i in range(len(initialMsrState)):
      msrNo, oldV = initialMsrState[i]
      assert curMsrValues[i].index == msrNo
      newV = curMsrValues[i].data
      if newV != oldV:
        print('Restoring original MSR value: 0x%08x: orig=0x%x, new=0x%x' % (msrNo, oldV, newV))
        addMsr(msrNo, oldV)

    addMsr(MSR_IA32_SYSENTER_CS, 0)
    addMsr(MSR_IA32_SYSENTER_ESP, 0)
    addMsr(MSR_IA32_SYSENTER_EIP, 0)
    addMsr(MSR_STAR, 0)
    addMsr(MSR_CSTAR, 0)
    addMsr(MSR_KERNEL_GS_BASE, 0)
    addMsr(MSR_SYSCALL_MASK, 0)
    addMsr(MSR_LSTAR, 0)
    addMsr(MSR_IA32_TSC, 0)
    addMsr(MSR_IA32_MISC_ENABLE, MSR_IA32_MISC_ENABLE__FAST_STRING)
    self.vcpu.setMsrs(msrs)

    #self.vcpu.setMsrs([kvmapi.KvmMsrEntry(0x2ff, 0, 0)])
    assert self.vcpu.getMsrs([0x2ff])[0].data == 0

  def _initVcpuLapic(self, vcpu):
    APIC_MODE_EXTINT = 0x7

    lapic = vcpu.lapic
    lapic.lvtLINT0 &= ~0x700
    lapic.lvtLINT0 |= APIC_MODE_EXTINT<<8
    lapic.lvtLINT1 &= ~0x700
    lapic.lvtLINT1 |= APIC_MODE_EXTINT<<8
    vcpu.lapic = lapic

  def _dumpRegs(self):
    regs = self.vcpu.regs
    print("  RAX=0x%016x" % regs.rax)
    print("  RIP=0x%016x" % regs.rip)
    print("  RFLAGS=0x%016x" % regs.rflags)

    sregs = self.vcpu.sregs
    print("  CR0=0x%08x CR4=0x%08x" % (sregs.cr0, sregs.cr4))
    print("  GDT=0x%08x L=0x%08x" % (sregs.gdt.base, sregs.gdt.limit))
    print("  CS=0x%04x B=0x%08x L=0x%08x " % (sregs.cs.selector, sregs.cs.base, sregs.cs.limit))
    print("  DS=0x%04x B=0x%08x L=0x%08x " % (sregs.ds.selector, sregs.ds.base, sregs.ds.limit))
    print("  EFER=0x%08x" % sregs.efer)
    #sregs.gdt.base = 0xF_FF30
    #self.vcpu.sregs = sregs
    sys.stdout.flush()

  def _describeCF8(self):
    cf8 = self._cf8 & 0x7FFF_FFFF
    regNo  = cf8 & 0xFF
    funcNo = (cf8>> 8)&0x07
    devNo  = (cf8>>11)&0x1F
    busNo  = (cf8>>16)&0xFF
    return '(%s:%s.%s) + 0x%02x' % (busNo,devNo,funcNo,regNo)

  def _handleIoRead(self, addr, width):
    if width == 1:
      return self._platform.iospace.read8(addr)
    elif width == 2:
      return self._platform.iospace.read16(addr)
    elif width == 4:
      return self._platform.iospace.read32(addr)
    else:
      raise Exception("invalid width")

  def _handleIoWrite(self, addr, v, width):
    if width == 1:
      self._platform.iospace.write8(addr, v)
    elif width == 2:
      self._platform.iospace.write16(addr, v)
    elif width == 4:
      self._platform.iospace.write32(addr, v)
    else:
      raise Exception("invalid width")

  def _handleMmioRead(self, addr, width):
    if width == 1:
      return self._platform.mspace.read8(addr)
    elif width == 2:
      return self._platform.mspace.read16(addr)
    elif width == 4:
      return self._platform.mspace.read32(addr)
    elif width == 8:
      return self._platform.mspace.read64(addr)
    else:
      raise Exception("invalid width")

  def _handleMmioWrite(self, addr, v, width):
    if width == 1:
      self._platform.mspace.write8(addr, v)
    elif width == 2:
      self._platform.mspace.write16(addr, v)
    elif width == 4:
      self._platform.mspace.write32(addr, v)
    elif width == 8:
      self._platform.mspace.write64(addr, v)
    else:
      raise Exception("invalid width")

  def runOnce(self):
    try:
      self.vcpu.runOnce()
    except InterruptedError as e:
      print("Interrupted")
      self._dumpRegs()
      return True
    except KeyboardInterrupt:
      print("Keyboard Interrupt")
      self._dumpRegs()
      self.i += 1
      return self.i < 2

    reason = self.vcpu.reason
    if reason == kvmapi.KvmExitReason.KVM_EXIT_UNKNOWN:
      print("unknown exit reason")
    elif reason == kvmapi.KvmExitReason.KVM_EXIT_DEBUG:
      dbg = self.vcpu.runData.exitReasons.debug
      print("exit debug: exc=0x%x pc=0x%x" % (dbg.exception, dbg.pc))
      self._dumpRegs()
    elif reason == kvmapi.KvmExitReason.KVM_EXIT_IO:
      io = self.vcpu.runData.exitReasons.io
      if io.direction: # out
        #r = self.vcpu.runBuf.seek(io.dataOffset)
        #r = self.vcpu.runBuf.read(io.size)
        r = bytearray(io.size)
        for i in range(io.size):
          r[i] = self.vcpu.runBuf[io.dataOffset+i]
        if io.size == 1:
          v = struct.unpack('<B', r)[0]
        elif io.size == 2:
          v = struct.unpack('<H', r)[0]
        elif io.size == 4:
          v = struct.unpack('<I', r)[0]
        else:
          raise Exception('...')
        if io.port != 0x402 and io.port != 0x3f8 and io.port != 0x3fd:
          print("exit I/O wr: 0x%x <- u%s(0x%x)" % (io.port, io.size*8, v))
        self._handleIoWrite(io.port, v, io.size)
      else: # in
        result = self._handleIoRead(io.port, io.size)
        if io.size == 1:
          buf = struct.pack('<B', result)
        elif io.size == 2:
          buf = struct.pack('<H', result)
        elif io.size == 4:
          buf = struct.pack('<I', result)
        else:
          raise Exception('...')

        #self.vcpu.runBuf.seek(io.dataOffset)
        #self.vcpu.runBuf.write(buf)
        for i in range(len(buf)):
          self.vcpu.runBuf[io.dataOffset+i] = buf[i]
        if io.port != 0x402 and io.port != 0x3f8 and io.port != 0x3fd:
          print("I/O rd: 0x%x -> u%s: 0x%x" % (io.port, io.size*8, result))

    elif reason == kvmapi.KvmExitReason.KVM_EXIT_MMIO: #direction size port count dataOffset
      mmio = self.vcpu.runData.exitReasons.mmio
      if mmio.isWrite:
        if mmio.len == 1:
          v = mmio.data[0] #struct.unpack('<B', mmio.data)[0]
        elif mmio.len == 2:
          v = struct.unpack('<H', bytes(mmio.data)[0:2])[0]
        elif mmio.len == 4:
          v = struct.unpack('<I', bytes(mmio.data)[0:4])[0]
        elif mmio.len == 8:
          v = struct.unpack('<Q', mmio.data)[0]
        else:
          raise Exception('...')

        self._handleMmioWrite(mmio.physAddr, v, mmio.len)
        print("exit MMIO: 0x%x <- u%d(0x%x)" % (mmio.physAddr, mmio.len*8, v))
      else:
        result = self._handleMmioRead(mmio.physAddr, mmio.len)
        if mmio.len == 1:
          buf = struct.pack('<B', result)
        elif mmio.len == 2:
          buf = struct.pack('<H', result)
        elif mmio.len == 4:
          buf = struct.pack('<I', result)
        elif mmio.len == 8:
          buf = struct.pack('<Q', result)
        else:
          raise Exception('...')

        for i in range(len(buf)):
          mmio.data[i] = buf[i]

        print("exit MMIO: 0x%x -> u%d" % (mmio.physAddr, mmio.len*8))

    elif reason == kvmapi.KvmExitReason.KVM_EXIT_INTR:
      print("exit INTR")
    elif reason == kvmapi.KvmExitReason.KVM_EXIT_SHUTDOWN:
      print("exit shutdown")
      return False
    elif reason == kvmapi.KvmExitReason.KVM_EXIT_SYSTEM_EVENT:
      print("exit system event")
    elif reason == kvmapi.KvmExitReason.KVM_EXIT_HLT:
      print("exit halt")
      return False
    else:
      print("other exit reason")

    return True

  def run(self):
    while True:
      if not self.runOnce():
        break
