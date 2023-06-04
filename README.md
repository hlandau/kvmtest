# kvmtest

An experimental VMM for KVM written in Python. This is simply an experimental
proof of concept which was hacked together enough to be able to boot OVMF, then
install Linux on a disk and boot it.

Mainly I wrote this to demonstrate how surprisingly easy the KVM API is to use.

Features:

  - Can boot OVMF UEFI
  - virtio-scsi interface featuring minimal block device and optical device emulation
  - SDL2 framebuffer (qxl) (install PySDL2)
  - PS/2 keyboard
  - Serial port

If you have any questions, don't hesitate to [contact
me](https://www.devever.net/~hl/contact) via IRC or email.

[**See article for introduction and demo video.**](https://www.devever.net/~hl/kvm)

## Example usage

### Nix users

Example usage for those with Nix installed, booting a [Debian
DVD](https://cdimage.debian.org/debian-cd/current/amd64/iso-dvd/debian-11.7.0-amd64-DVD-1.iso):
```
$ nix-shell -p python3Packages.pysdl2 OVMF.fd
$ OVMF="$(cat "$buildInputs" | tr ' ' '\n' | grep OVMF)"
$ cp "$OVMF/FV/OVMF_VARS.fd" ./
$ chmod +w OVMF_VARS.fd
$ qemu-img create -f raw test.bin 8G
$ ./kvm.py \
  -fwcode $OVMF/FV/OVMF_CODE.fd \
  -fwvars OVMF_VARS.fd \
  -optical debian-11.7.0-amd64-DVD-1.iso \
  -disk test.bin
```

### Other users

If you don't have Nix installed, you can get a [prebuilt demo OVMF image from
here to play with](https://www.devever.net/~hl/f/OVMF-Demo-Image.tar.gz). Pass
the paths to `OVMF_CODE.fd` and `OVMF_VARS.fd` to `kvm.py`, ensuring that
`OVMF_VARS.fd` is writable. You will also need Python 3 and PySDL2 installed.
You will also need an optical media image to boot, [such as a Debian
DVD.](https://cdimage.debian.org/debian-cd/current/amd64/iso-dvd/debian-11.7.0-amd64-DVD-1.iso)
```
$ qemu-img create -f raw test.bin 8G
$ ./kvm.py \
  -fwcode $OVMF/FV/OVMF_CODE.fd \
  -fwvars OVMF_VARS.fd \
  -optical debian-11.7.0-amd64-DVD-1.iso \
  -disk test.bin
```

## Known issues

This is just a demo of the KVM API. It was hacked together to demonstrate the
KVM API, so don't expect the code to be very clean.

  - Arch Linux won't detect the PS/2 keyboard in the live ISO due to lack of working
    ACPI. Pass `earlymodules=i8042,atkbd` on the kernel command line.

  - Debian 10's installer works (in text mode), until it tries to install
    grub-uefi, where it fails for whatever reason.

  - Debian 10's graphical installer won't work currently.

  - No network devices are implemented.

## Licence

```
2021 Hugo Landau <hlandau@devever.net>
```

Files not otherwise marked are licenced under the MIT License.
