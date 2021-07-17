import struct

SCSI_TASK_ATTR__SIMPLE         = 0
SCSI_TASK_ATTR__ORDERED        = 1
SCSI_TASK_ATTR__HEAD_OF_QUEUE  = 2
SCSI_TASK_ATTR__ACA            = 3

SCSI_STATUS__GOOD                  = 0x00
SCSI_STATUS__CHECK_CONDITION       = 0x02
SCSI_STATUS__CONDITION_MET         = 0x04
SCSI_STATUS__BUSY                  = 0x08
SCSI_STATUS__RESERVATION_CONFLICT  = 0x18
SCSI_STATUS__TASK_SET_FULL         = 0x28
SCSI_STATUS__ACA_ACTIVE            = 0x30
SCSI_STATUS__TASK_ABORTED          = 0x40

SCSI_TMF_RES__FUNCTION_COMPLETE    = 0
SCSI_TMF_RES__FUNCTION_SUCCEEDED   = 1
SCSI_TMF_RES__FUNCTION_REJECTED    = 2
SCSI_TMF_RES__INCORRECT_LUN        = 3

SCSI_SENSE_KEY__NO_SENSE    = 0x0
SCSI_SENSE_KEY__HW_ERROR    = 0x4
SCSI_SENSE_KEY__ILLEGAL_REQ = 0x5

class ScsiException(Exception):
  pass

class ScsiServiceDeliveryOrTargetFailureException(ScsiException):
  pass

# Represents the arguments to the SCSI Execute Command procedure call.
class ScsiCmd:
  # dataOutBuf, if given, is a buffer object supporting seeks and reads.
  # It must also have a special attribute .len indicating the total
  # amount which can be read from it in bytes.
  #
  # dataInBuf, if given, is a buffer object supporting seeks and writes.
  # It must also have a special attribute .len indicating the total
  # amount which can be written to it in bytes.
  #
  # (lun: u64, id: u64, cdb: bytes, taskAttr: TASk_ATTR__*, crn: u8?,
  #  priority: u4?, dataOutBuf: buffer?, dataInBuf: buffer?) → ScsiCmd
  def __init__(self, *, lun, id, cdb, taskAttr=SCSI_TASK_ATTR__SIMPLE, crn=None, priority=0, dataOutBuf=None, dataInBuf=None):
    assert len(cdb) >= 6
    assert taskAttr in (SCSI_TASK_ATTR__SIMPLE, SCSI_TASK_ATTR__ORDERED,
      SCSI_TASK_ATTR__HEAD_OF_QUEUE, SCSI_TASK_ATTR__ACA)
    assert priority >= 0 and priority <= 0xF
    self.lun        = lun
    self.id         = id
    self.cdb        = cdb
    print('@Virtio: new cmd, cdb=%s' % self.cdb)
    self.taskAttr   = taskAttr
    self.crn        = crn
    self.priority   = priority
    self.dataOutBuf = dataOutBuf
    self.dataInBuf  = dataInBuf

  def __repr__(self):
    return f"ScsiCmd(lun=0x%x, id=0x%x, cdbOpcode=0x%02x)" % (self.lun, self.id, self.cdb[0])

# Represents a category of SCSI sense response which can be used to generate
# SCSI sense data.
class ScsiSenseTemplate:
  def __init__(self, key, asc, ascq):
    self.key  = key
    self.asc  = asc
    self.ascq = ascq

  def make(self):
    return struct.pack('!BBBIBIBBBBBB', 0x70, 0,
      self.key & 0xF,
      0,                # info
      0,                # additionalLen
      0,                # csInfo
      self.asc,         # ASC
      self.ascq,        # ASCQ
      0,                # FRU Code
      0,                # Sense Key Specific 0
      0,                # Sense Key Specific 1
      0)                # Sense Key Specific 2

SCSI_ST__INVALID_COMMAND_OPERATION_CODE = ScsiSenseTemplate(SCSI_SENSE_KEY__ILLEGAL_REQ, 0x20, 0x00)
SCSI_ST__LBA_OUT_OF_RANGE               = ScsiSenseTemplate(SCSI_SENSE_KEY__ILLEGAL_REQ, 0x21, 0x00)
SCSI_ST__INVALID_FIELD_IN_CDB           = ScsiSenseTemplate(SCSI_SENSE_KEY__ILLEGAL_REQ, 0x24, 0x00)
SCSI_ST__LOGICAL_UNIT_NOT_SUPPORTED     = ScsiSenseTemplate(SCSI_SENSE_KEY__ILLEGAL_REQ, 0x25, 0x00)
SCSI_ST__LOGICAL_UNIT_FAILURE           = ScsiSenseTemplate(SCSI_SENSE_KEY__HW_ERROR,    0x3E, 0x01)
SCSI_ST__INTERNAL_TARGET_FAILURE        = ScsiSenseTemplate(SCSI_SENSE_KEY__HW_ERROR,    0x44, 0x00)
SCSI_ST__NONE                           = ScsiSenseTemplate(SCSI_SENSE_KEY__NO_SENSE,    0x00, 0x00)

# Represents the results of a successful SCSI Execute Command procedure call.
class ScsiResult:
  # (senseData: bytes, status: u8, statusQualifier: u16?) → ScsiResult
  def __init__(self, *, senseData, status, statusQualifier=None):
    self.senseData        = senseData
    self.status           = status
    self.statusQualifier  = statusQualifier

  def __repr__(self):
    return f"ScsiResult(status=0x%x/0x%x)" % (self.status, self.statusQualifier)

  @classmethod
  def good(cls):
    return ScsiResult(senseData=None, status=SCSI_STATUS__GOOD)

  @classmethod
  def checkCondition(cls, senseData, **kwargs):
    if isinstance(senseData, ScsiSenseTemplate):
      senseData = senseData.make(**kwargs)
    elif not isinstance(senseData, bytes):
      raise Exception("sense data must be a ScsiSenseTemplate or bytes object: %s" % senseData)

    return ScsiResult(senseData=senseData, status=SCSI_STATUS__CHECK_CONDITION)

# Abstract representation of an SCSI Service Delivery Subsystem as defined by
# SAM-4.
class IScsiSubsystem:
  # Abstract definition of the Execute Command procedure call as defined in SAM-4.
  # The arguments defined in SAM-4 are encapsulated in a ScsiCmd object.
  # The I_T_L_Q nexus is represented a (LUN, Command ID) tuple.
  #
  # Either a ScsiResult is returned (corresponding to a service response of
  # Command Complete) or a ServiceDeliveryOrTargetFailureException is thrown.
  #
  # (req: ScsiCmd) → ScsiResult | throw ScsiServiceDeliveryOrTargetFailureException
  def executeCommand(self, req):
    raise NotImplementedError()

  # The following functions implement the different task management function
  # procedure calls as defined by SAM-4. The nexus is given by the lun or (lun,
  # id) arguments.
  #
  # The service responses of Function Complete, Function Succeeded, Function Rejected
  # and Incorrect Logical Unit Number are represented by returning TMF_RES__*.
  # A ScsiServiceDeliveryOrTargetFailureException corresponds to a service
  # response of Service Delivery or Target Failure.
  #
  # (lun: u64, id: u64) → ()
  def abortTask(self, lun, id):
    raise NotImplementedError()

  def abortTaskSet(self, lun):
    raise NotImplementedError()

  def clearAca(self, lun):
    raise NotImplementedError()

  def clearTaskSet(self, lun):
    raise NotImplementedError()

  def itNexusReset(self):
    raise NotImplementedError()

  def luReset(self, lun):
    raise NotImplementedError()

  def queryTask(self, lun, id):
    raise NotImplementedError()

  def queryTaskSet(self, lun):
    raise NotImplementedError()

  def queryAsyncEvent(self, lun):
    raise NotImplementedError()

  # The following functions correspond to the event notification SCSI transport
  # protocol services given in SAM-4.

  # () → ()
  def nexusLoss(self):
    pass

  # () → ()
  def transportReset(self):
    pass

  # () → ()
  def powerLossExpected(self):
    pass

class ScsiDevice(IScsiSubsystem):
  def __init__(self, subsystem):
    self.subsystem = subsystem

  def executeCommand(self, req):
    r = self._executeCommand(req)
    self._lastSenseData = r.senseData
    return r

  def _executeCommand(self, req):
    opcode = req.cdb[0]
    if opcode == 0x00: # TEST UNIT READY
      return self._handleTEST_UNIT_READY(req)
    elif opcode == 0x03: # REQUEST SENSE
      return self._handleREQUEST_SENSE(req)
    elif opcode == 0x12: # INQUIRY
      print('@Virtio: as inquiry')
      return self._handleINQUIRY(req)
    else:
      print('@Virtio: as unhandled 0x%x' % req.cdb[0])
      return ScsiResult.checkCondition(SCSI_ST__INVALID_COMMAND_OPERATION_CODE)

  @property
  def peripheralDeviceType(self):
    raise NotImplementedError("must set periperalDeviceType")

  @property
  def t10VendorID(self):
    raise NotImplementedError("must set T10 vendor ID to a bytestring not exceeding eight bytes")

  @property
  def t10VendorSubID(self):
    raise NotImplementedError("must set T10 vendor ID to a bytestring")

  @property
  def eui64(self):
    raise NotImplementedError("must set eui64 to an EUI-64 unique ID")

  version = 0x04 # SPC-2

  @property
  def vendorID(self):
    raise NotImplementedError("must set vendorID to bytestring not exceeding eight bytes")

  @property
  def productID(self):
    raise NotImplementedError("must set productID to a bytestring not exceeding sixteen bytes")

  @property
  def productRev(self):
    raise NotImplementedError("must set productRev to a bytestring not exceeding four bytes")

  @property
  def versionDescriptors(self):
    raise NotImplementedError("must set versionDescriptors to a tuple of shorts")

  def _handleTEST_UNIT_READY(self, req):
    return ScsiResult.good()

  def _handleREQUEST_SENSE(self, req):
    maxLen = req.cdb[4]
    useDesc = req.cdb[1] & 1
    if useDesc:
      return ScsiResult.checkCondition(SCSI_ST__INVALID_FIELD_IN_CDB)

    if self._lastSenseData is None:
      req.dataInBuf.write(SCSI_ST__NONE.make()[:maxLen])
    else:
      req.dataInBuf.write(self._lastSenseData[:maxLen])

    return ScsiResult.good()

  def _handleINQUIRY(self, req):
    cmdDt     = req.cdb[1] & 2
    evpd      = req.cdb[1] & 1
    page      = req.cdb[2]
    allocLen  = req.cdb[4]
    control   = req.cdb[5]

    periQual        = 0
    periDeviceType  = self.peripheralDeviceType

    if evpd:
      print('@Virtio: evpd req')
      if cmdDt:
        return ScsiResult.checkCondition(SCSI_ST__INVALID_FIELD_IN_CDB)
      if page == 0x00: # Supported VPD Pages
        pageList = [0x00, 0x83]
        pageData = struct.pack('!BBBB', periDeviceType | (periQual<<5), 0x00, 0, len(pageList)) + bytes(pageList)
        req.dataInBuf.write(pageData)
        return ScsiResult.good()
      elif page == 0x83: # Device Identification
        t10VendorID = self.t10VendorID.ljust(8, b' ')
        if len(t10VendorID) > 8:
          raise Exception("T10 vendor ID must not exceed 8 characters: %r" % t10VendorID)

        t10VendorSubID = self.t10VendorSubID
        ident     = t10VendorID + t10VendorSubID
        ident2    = self.eui64
        pageBody  = struct.pack('!BBBB', 2, 1, 0, len(ident)) + ident
        pageBody += struct.pack('!BBBB', 1, 2, 0, len(ident2)) + ident2
        pageData  = struct.pack('!BBBB', periDeviceType | (periQual<<5), 0x83, 0, len(pageBody)) + pageBody
        req.dataInBuf.write(pageData)
        return ScsiResult.good()
      else:
        return ScsiResult.checkCondition(SCSI_ST__INVALID_FIELD_IN_CDB)

    if cmdDt or page:
      print('@Virtio: bad page')
      return ScsiResult.checkCondition(SCSI_ST__INVALID_FIELD_IN_CDB)

    version = self.version

    vendorID    = self.vendorID.ljust(8, b' ')
    if len(vendorID) > 8:
      raise Exception("vendor ID must not exceed 8 characters: %r", vendorID)

    productID   = self.productID.ljust(16, b' ')
    if len(productID) > 16:
      raise Exception("product ID must not exceed 16 characters: %r", productID)

    productRev  = self.productRev.ljust(4, b' ')
    if len(productRev) > 8:
      raise Exception("product revision must not exceed 4 characters: %r", productRev)

    additionalLen = 0

    versionDescriptors = list(self.versionDescriptors)
    if len(versionDescriptors) > 8:
      raise Exception("cannot have more than eight version descriptors")
    while len(versionDescriptors) < 8:
      versionDescriptors.append(0)

    inquiryData = struct.pack('!8B8s16s4s20sBB8H22s',
      periDeviceType | (periQual << 5),
      0,
      version,
      2,
      additionalLen,
      0,
      0,
      0,
      vendorID,
      productID,
      productRev,
      b'\0'*20,
      0,
      0,
      versionDescriptors[0], versionDescriptors[1], versionDescriptors[2], versionDescriptors[3],
      versionDescriptors[4], versionDescriptors[5], versionDescriptors[6], versionDescriptors[7],
      b'\0'*22)

    if len(inquiryData) > req.dataInBuf.len:
      inquiryData = inquiryData[0:req.dataInBuf.len]

    print('@Virtio: inquiry handled normally')
    req.dataInBuf.write(inquiryData)
    return ScsiResult.good()

class ScsiBlockDeviceBase(ScsiDevice):
  peripheralDeviceType= 0x00 # SBC
  t10VendorID         = b'DEVEVER'
  t10VendorSubID      = b'BLKDEV'
  eui64               = b'\x11\x22\x33\x44\x11\x22\x33\x44'
  vendorID            = b'DEVEVER'
  productID           = b'BLKDEV'
  productRev          = b'0'
  versionDescriptors  = (0x0080, 0x0600) # SAM-4, SBC-4
  blockSize           = 512
  _openMode           = 'rb'

  def __init__(self, subsystem, fn):
    super().__init__(subsystem)
    self._f = open(fn, self._openMode)
    self._f.seek(0, 2)
    self._capacity = self._f.tell()

  def _executeCommand(self, req):
    opcode = req.cdb[0]
    if opcode == 0x25: # READ CAPACITY (10)
      return self._handleREAD_CAPACITY_10(req)
    elif opcode == 0x28: # READ (10)
      return self._handleREAD_10(req)
      # 0xA0  REPORT LUNS
      # 0x1A  MODE SENSE(6)
    elif opcode == 0x1A: # MODE SENSE (6)
      return self._handleMODE_SENSE_6(req)
    else:
      return super()._executeCommand(req)

  def _handleREAD_CAPACITY_10(self, req):
    if len(req.cdb) < 10:
      return ScsiResult.checkCondition(SCSI_ST__INVALID_FIELD_IN_CDB)

    lba = struct.unpack('>I', req.cdb[2:6])[0]
    if lba or req.cdb[8] & 1:
      return ScsiResult.checkCondition(SCSI_ST__INVALID_FIELD_IN_CDB)

    bytesPerLba = self.blockSize
    numLba      = self._capacity//bytesPerLba

    if numLba > 0xFFFF_FFFF:
      numLba = 0xFFFF_FFFF

    req.dataInBuf.write(struct.pack('>II', numLba, bytesPerLba))
    return ScsiResult.good()

  def _handleREAD_10(self, req):
    if len(req.cdb) < 10:
      return ScsiResult.checkCondition(SCSI_ST__INVALID_FIELD_IN_CDB)

    lba, groupNo, xferLen = struct.unpack('>IBH', req.cdb[2:9])
    print('@Virtio: reading LBA %s, count %s' % (lba, xferLen))
    self._f.seek(lba*self.blockSize)
    for i in range(xferLen):
      d = self._f.read(self.blockSize)
      req.dataInBuf.write(d)
    return ScsiResult.good()

  def _handleMODE_SENSE_6(self, req):
    pageCode      = req.cdb[2]
    pc            = pageCode>>6
    pageCode      = pageCode & 0x3F
    subPageCode   = req.cdb[3]
    print('@Virtio: unhandled MODE SENSE (6) pc=0x%x pageCode=0x%x subPageCode=0x%x' % (pc, pageCode, subPageCode))
    return ScsiResult.checkCondition(SCSI_ST__INVALID_COMMAND_OPERATION_CODE)

class ScsiBlockDevice(ScsiBlockDeviceBase):
  peripheralDeviceType  = 0x00 # SBC
  _openMode             = 'r+b'

  def _executeCommand(self, req):
    opcode = req.cdb[0]
    if opcode == 0x2A: # WRITE (10)
      return self._handleWRITE_10(req)
    elif opcode == 0x41: # WRITE SAME (10)
      return self._handleWRITE_SAME_10(req)
    else:
      return super()._executeCommand(req)

  def _handleWRITE_10(self, req):
    if len(req.cdb) < 10:
      return ScsiResult.checkCondition(SCSI_ST__INVALID_FIELD_IN_CDB)

    lba, groupNo, xferLen = struct.unpack('>IBH', req.cdb[2:9])
    print('@Virtio: writing LBA %s, count %s' % (lba, xferLen))
    self._f.seek(lba*self.blockSize)
    for i in range(xferLen):
      d = req.dataOutBuf.read(self.blockSize)
      assert len(d) == self.blockSize
      self._f.write(d)

    return ScsiResult.good()

  def _handleWRITE_SAME_10(self, req):
    if len(req.cdb) < 10:
      return ScsiResult.checkCondition(SCSI_ST__INVALID_FIELD_IN_CDB)

    lba, groupNo, xferLen = struct.unpack('>IBH', req.cdb[2:9])
    print('@Virtio: writing-same LBA %s, count %s' % (lba, xferLen))

    lbdata = req.cdb[1] & (1<<1)
    pbdata = req.cdb[1] & (1<<2)
    if lbdata or pbdata:
      return ScsiResult.checkCondition(SCSI_ST__INVALID_FIELD_IN_CDB)

    d = req.dataOutBuf.read(self.blockSize)
    assert len(d) == self.blockSize

    self._f.seek(lba*self.blockSize)
    for i in range(xferLen):
      self._f.write(d)

    return ScsiResult.good()

class ScsiOpticalDevice(ScsiBlockDeviceBase):
  peripheralDeviceType  = 0x05 # MMC
  blockSize             = 2048

  def _executeCommand(self, req):
    opcode = req.cdb[0]
    # We must be able to generate DISK_EJECT_REQUEST="",
    # ID_CDROM_MEDIA_TRACK_COUNT_DATA="?*",
    # ID_CDROM_MEDIA_SESSION_LAST_OFFSET="?*" or Arch Linux ISOs will not boot
    # because udev will not recognise the optical drive as having media
    # inserted according to its default rules and not run the blkid scanner,
    # which in turn means the label of the ISO's filesystem is not determined
    # and /dev/disk/by-label/... is not created, which is what the initrd
    # expects to mount as the root FS.
    #
    # In order to get ID_CDROM_MEDIA_TRACK_COUNT_DATA, we need to implement
    # READ TOC/PMA/ATIP(Format=0 "TOC", Track/Session Number=1) and
    # READ TOC/PMA/ATIP(Format=0 "TOC", Track/Session Number=X).
    # In order to get ID_CDROM_MEDIA_SESSION_LAST_OFFSET, we need to implement
    # Perhaps also READ TOC/PMA/ATIP(Format=1 "Session Info")
    #
    # udev's scanner utility, cdrom_id, will not issue READ TOC/PMA/ATIP
    # however unless GET CONFIGURATION(StartingFeature=0, RT=0) is implemented,
    # so we need to implement that too.
    if opcode == 0x43: # READ TOC/PMA/ATIP
      return self._handleREAD_TOC_PMA_ATIP(req)
    #elif opcode == 0x51: # READ DISC INFORMATION
    #  pass
    elif opcode == 0x46: # GET CONFIGURATION
      return self._handleGET_CONFIGURATION(req)
    else:
      return super()._executeCommand(req)
      # 0x4A  GET EVENT STATUS NOTIFICATION
      # 0x43  READ TOC/PMA/ATIP
      # 0x51  READ DISC INFORMATION
      # 0x46  GET CONFIGURATION *

  def _handleREAD_TOC_PMA_ATIP(self, req):
    format          = req.cdb[2] & 0xF
    trackSessionNo  = req.cdb[6]

    if format == 0: # TOC
      return self._handleREAD_TOC_PMA_ATIP__TOC(req, trackSessionNo)
    elif format == 1: # Session Info
      return self._handleREAD_TOC_PMA_ATIP__SessionInfo(req, trackSessionNo)
    else:
      return ScsiResult.checkCondition(SCSI_ST__INVALID_FIELD_IN_CDB)

  def _handleREAD_TOC_PMA_ATIP__TOC(self, req, trackSessionNo):
    # From qemu hw/block/cdrom.c
    firstTrack = 1
    lastTrack  = 1

    if trackSessionNo > 1 and trackSessionNo != 0xAA:
      return ScsiResult.checkCondition(SCSI_ST__INVALID_FIELD_IN_CDB)

    data = b''
    if trackSessionNo <= 1:
      adrCtrl = 0x14
      trackNo = 1
      lba     = 0
      data += struct.pack('>BBBBI', 0, adrCtrl, trackNo, 0, lba)

    adrCtrl = 0x16
    trackNo = 0xAA
    lba     = self._capacity//self.blockSize
    data += struct.pack('>BBBBI', 0, adrCtrl, trackNo, 0, lba)

    b = struct.pack('>HBB', len(data), firstTrack, lastTrack) + data
    req.dataInBuf.write(b)
    return ScsiResult.good()

  def _handleREAD_TOC_PMA_ATIP__SessionInfo(self, req, trackSessionNo):
    firstSession  = 1
    lastSession   = 1

    adrCtrl       = 0b0100 # Data track recorded uninterrupted
    trackNo       = 1
    lba           = 0

    data = struct.pack('>BBBBI', 0, adrCtrl, trackNo, 0, lba)

    b = struct.pack('>HBB', len(data), firstSession, lastSession) + data
    req.dataInBuf.write(b)
    return ScsiResult.good()

  def _handleGET_CONFIGURATION(self, req):
    curProfile = 0x40 # BD-ROM
    data = struct.pack('>HH', 0, curProfile)

    features = (
      (0x0000,0x3),        # Profile List
      (0x0001,0xB),        # Core
      (0x0040,0x5),        # BD Read
      )

    for featureCode, flags in features:
      additionalData = b''
      if featureCode == 0x0000: # Profile List
        profileNo = 0x0040 # BD-ROM
        additionalData = struct.pack('>HBB', profileNo, 1, 0)
      elif featureCode == 0x0001: # Core
        # N.B. Implementing this requires one to support
        #   GET CONFIGURATION, GET EVENT STATUS NOTIFICATION,
        #   MODE SELECT (10), MODE SENSE (10)
        physIntfStd   = 1 # SCSI Family
        coreFlags     = 1
        additionalData = struct.pack('>IBBBB', physIntfStd, coreFlags, 0, 0, 0)
      elif featureCode == 0x0040: # BD Read
        flags0 = 0
        flags1 = (1<<1) | (1<<2) # Support reading BD-RE
        flags2 = (1<<1) # Support reading BD-R
        flags3 = (1<<1) # Support reading BD-ROM
        additionalData = struct.pack('>B4xB2xB2xBx', flags0, flags1, flags2, flags3)

      data += struct.pack('>HBB', featureCode, flags, len(additionalData)) + additionalData

    data = struct.pack('>I', len(data)) + data
    req.dataInBuf.write(data)
    return ScsiResult.good()

class ScsiReportLunsLU(IScsiSubsystem):
  def __init__(self, subsystem):
    self.subsystem = subsystem

  def executeCommand(self, req):
    opcode = req.cdb[0]
    if opcode == 0xA0: # REPORT LUNS
      return self._handleREPORT_LUNS(req)
    elif opcode == 0x12: # INQUIRY
      return self._handleINQUIRY(req)
    else:
      return ScsiResult.checkCondition(SCSI_ST__INVALID_COMMAND_OPERATION_CODE)

# A SCSI subsystem which routes via LUN.
class ScsiSubsystem(IScsiSubsystem):
  def __init__(self, *, diskPath=None, opticalPath=None):
    self._luns = {}
    #self.registerLun(0xC101_0000_0000_0000, ScsiReportLunsLU(self))
    if opticalPath:
      self.blk0 = self.registerLun(0x0100_4000_0000_0000, ScsiOpticalDevice(self, fn=opticalPath))
    if diskPath:
      self.blk1 = self.registerLun(0x0100_4001_0000_0000, ScsiBlockDevice(self, fn=diskPath))

  def registerLun(self, id, lun):
    self._luns[id] = lun
    return lun

  def executeCommand(self, req):
    lun = self._luns.get(req.lun)
    if lun:
      return lun.executeCommand(req)

    print('@Virtio: LU not supported')
    return ScsiResult.checkCondition(SCSI_ST__LOGICAL_UNIT_NOT_SUPPORTED)
