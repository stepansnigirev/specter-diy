# detect if it's a hardware device or linuxport
import sys
import os
import pyb
import gc

simulator = sys.platform != "pyboard"

try:
    import config
except:
    import config_default as config


class CriticalErrorWipeImmediately(Exception):
    """
    This exception should be raised when device needs to be wiped
    because something terrible happened
    """

    pass


def maybe_mkdir(path):
    try:
        os.mkdir(path)
    except:
        pass
    if not simulator:
        os.sync()


def fpath(fname):
    """A small function to avoid % storage_root everywhere"""
    return "%s%s" % (config.storage_root, fname)


sdcard = None  # SD card instance
sdled = None  # LED to show we are working with SD card

# path to store #reckless entropy
if simulator:
    # create folders for simulator
    maybe_mkdir(config.storage_root)
    maybe_mkdir(fpath("/flash"))
    maybe_mkdir(fpath("/qspi"))
    maybe_mkdir(fpath("/sd"))
else:
    storage_root = ""
    sdcard = pyb.SDCard()
    sdled = pyb.LED(4)
    sdled.off()


def is_sd_present() -> bool:
    """
    Checks if SD card is inserted
    """
    # simulator
    if sdcard is None:
        return True
    return sdcard.present()


def mount_sdcard() -> bool:
    """Mounts SD card"""
    if not is_sd_present():
        raise RuntimeError("SD card is not present")
    if sdcard is not None:
        sdled.on()
        sdcard.power(True)
        os.mount(sdcard, "/sd")


def unmount_sdcard() -> bool:
    """Unmounts SD card"""
    # sync file system before unmounting
    if not is_sd_present():
        raise RuntimeError("SD card is not present")
    if sdcard is not None:
        os.sync()
        os.umount("/sd")
        sdcard.power(False)
        sdled.off()


def mount_sdram():
    path = fpath("/ramdisk")
    if simulator:
        # not a real RAM on simulator
        maybe_mkdir(path)
        # cleanup
        delete_recursively(path)
    else:
        import sdram

        sdram.init()
        bdev = sdram.RAMDevice(512)
        os.VfsFat.mkfs(bdev)
        os.mount(bdev, path)
    return path


def sync():
    try:
        os.sync()
    except:
        pass


def file_exists(fname: str) -> bool:
    try:
        with open(fname, "rb") as f:
            pass
        return True
    except:
        return False


def delete_recursively(path, include_self=False):
    # remove trailing slash
    path = path.rstrip("/")
    files = os.ilistdir(path)
    for _file in files:
        if _file[0] in [".", ".."]:
            continue
        f = "%s/%s" % (path, _file[0])
        # regular file
        if _file[1] == 0x8000:
            os.remove(f)
        # directory
        elif _file[1] == 0x4000:
            delete_recursively(f)
            os.rmdir(f)

    files = os.ilistdir(path)
    num_of_files = sum(1 for _ in files)
    if (num_of_files == 2 and simulator) or num_of_files == 0:
        """
        Directory is empty - it contains exactly 2 directories -
        current directory and parent directory (unix) or
        0 directories (stm32)
        """
        if include_self:
            os.rmdir(path)
        return True
    raise RuntimeError("Failed to delete folder %s" % path)


if not simulator:
    stlk = pyb.UART("YB", 9600)


def set_usb_mode(dev=False, usb=False):
    if simulator:
        print("dev:", dev, ", usb:", usb)
    # now get correct mode
    if usb and not dev:
        pyb.usb_mode("VCP")
        if not simulator:
            os.dupterm(None, 0)
            os.dupterm(None, 1)
    elif usb and dev:
        pyb.usb_mode("VCP+MSC")
        if not simulator:
            # duplicate repl to stlink
            # as usb is busy for communication
            os.dupterm(stlk, 0)
            os.dupterm(None, 1)
    elif not usb and dev:
        pyb.usb_mode("VCP+MSC")
        usb = pyb.USB_VCP()
        if not simulator:
            os.dupterm(None, 0)
            os.dupterm(usb, 1)
    else:
        pyb.usb_mode(None)
        if not simulator:
            os.dupterm(None, 0)
            os.dupterm(None, 1)


def reboot():
    if simulator:
        sys.exit()
    else:
        pyb.hard_reset()


def wipe():
    """
    Blocks map in disco board
    0: MBR
    1   - 255:   reserved
    256 - 447:   internal flash
    448 - 33215: QSPI
    """
    delete_recursively(fpath("/flash"))
    delete_recursively(fpath("/qspi"))
    if not simulator:
        os.umount("/flash")
        os.umount("/qspi")
        f = pyb.Flash()
        block_size = f.ioctl(5, None)
        # wipe internal flash with random bytes
        for i in range(256, 450):
            b = os.urandom(block_size)
            f.writeblocks(i, b)
            del b
            gc.collect()
    # mpy will reformat fs on reboot
    reboot()


def usb_connected():
    if simulator:
        return True
    return bool(pyb.Pin.board.USB_VBUS.value())
