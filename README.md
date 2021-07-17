# kvmtest

An experimental VMM for KVM written in Python. This is simply an experimental
proof of concept which was hacked together enough to be able to boot OVMF, then
install Linux on a disk and boot it.

Mainly I wrote this to demonstrate how surprisingly easy the KVM API is to use.

Features:

  - Can boot OVMF
  - virtio-scsi interface featuring minimal block device and optical device emulation
  - SDL2 framebuffer (qxl) (install PySDL2)
  - PS/2 keyboard
  - Serial port

Example usage:

```
$ qemu-img create -f raw test.bin 8G
$ ./kvm.py -fwcode OVMF_CODE.fd -fwvars OVMF_VARS.fd -cdrom debian.iso -disk test.bin
```

If you have any questions, don't hesitate to [contact
me](https://www.devever.net/~hl/contact) via IRC or email.

## Known issues

  - Arch Linux won't detect the PS/2 keyboard in the live ISO due to lack of working
    ACPI. Pass `earlymodules=i8042,atkbd` on the kernel command line.

  - Debian 10's installer works, until it tries to install grub-uefi, where it fails for
    whatever reason.

  - No network devices are implemented.
