#!/usr/bin/env python3
import sys, argparse, os, fcntl, enum, mmap, struct, signal
import kvmo, kvmapi
from x86 import *
from iodev_qemu import *
from vmm import *

def run():
  sys.stdout.reconfigure(line_buffering=True)
  sys.stderr.reconfigure(line_buffering=True)

  ap = argparse.ArgumentParser()
  ap.add_argument('-fwcode', metavar='OVMF_CODE.fd')
  ap.add_argument('-fwvars', metavar='OVMF_VARS.fd')
  ap.add_argument('-disk', metavar='path.bin')
  ap.add_argument('-optical', metavar='path.iso')
  args = vars(ap.parse_args())

  if args['fwcode'] is None or args['fwvars'] is None:
    print('Must provide -fwcode and -fwvars with paths to OVMF_CODE.fd and OVMF_VARS.fd')
    return 1

  vmm = VMM(platformFunc=Q35Platform, firmwarePath=args['fwcode'],
    firmwareVarsPath=args['fwvars'], opticalPath=args['optical'], diskPath=args['disk'])
  vmm.run()
  return 0

if __name__ == '__main__':
  sys.exit(run())
