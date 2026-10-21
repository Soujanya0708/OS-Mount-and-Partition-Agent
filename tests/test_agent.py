"""
Tests for intent parsing, filesystem sniffing and the mount/unmount flow on both platforms (dry-run).
Run from mount_agent_terminal/:   python -m unittest discover tests
"""

import os
import tempfile
import unittest

from mountagent.agent.backends import OfflineBackend
from mountagent.agent.heuristic import parse
from mountagent.agent.tools import ToolBox
from mountagent.core import fsdetect
from mountagent.core.platforms import get_platform
from mountagent.core.runner import Runner
from mountagent.core.session import Session


def make_box(platform):
    session = Session()
    return ToolBox(get_platform(platform, Runner(dry_run=True)), session), session


class TestIntentParsing(unittest.TestCase):
    def setUp(self):
        self.session = Session()

    def tools(self, prompt):
        plan = parse(prompt, self.session)
        return [step[0] for step in plan.steps] if plan else None

    def test_mount_iso_and_browse(self):
        plan = parse("Mount this ubuntu.iso file so I can look at the files inside.", self.session)
        self.assertEqual(plan.steps[0], ("mount", {"source": "ubuntu.iso", "read_only": True}))
        self.assertEqual(plan.steps[1][0], "list_files")

    def test_mount_device_read_write_at_path(self):
        plan = parse("mount /dev/sdb1 read-write at /mnt/usb", self.session)
        self.assertEqual(plan.steps[0][1],
                         {"source": "/dev/sdb1", "read_only": False, "mount_point": "/mnt/usb"})

    def test_partition_number(self):
        plan = parse("mount disk.img partition 2", self.session)
        self.assertEqual(plan.steps[0][1]["partition"], 2)

    def test_windows_phrasing(self):
        plan = parse(r"mount C:\Users\me\Downloads\ubuntu.iso", self.session)
        self.assertEqual(plan.steps[0][1]["source"], r"C:\Users\me\Downloads\ubuntu.iso")
        plan = parse("mount partition 1 of disk 1", self.session)
        self.assertEqual(plan.steps[0][1], {"source": "disk1", "read_only": True, "partition": 1})
        self.assertEqual(parse("unmount D:", self.session).steps, [("unmount", {"target": "D:"})])
        self.assertEqual(self.tools("show files in D:"), ["list_files"])
        self.assertEqual(self.tools("which images are attached?"), ["list_attached_images"])

    def test_other_intents(self):
        self.assertEqual(self.tools("show me all disks and partitions"), ["list_block_devices"])
        self.assertEqual(self.tools("which loop devices are in use?"), ["list_attached_images"])
        self.assertEqual(self.tools("what filesystem is backup.img?"), ["inspect_filesystem"])
        self.assertEqual(self.tools("show files in /mnt/agent/ubuntu"), ["list_files"])
        self.assertEqual(self.tools("unmount /mnt/agent/ubuntu"), ["unmount"])
        self.assertIsNone(self.tools("make me a sandwich"))


class TestFilesystemSniffing(unittest.TestCase):
    def sniff_bytes(self, data: bytes):
        fd, path = tempfile.mkstemp()
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        try:
            return fsdetect.sniff(path)
        finally:
            os.remove(path)

    def test_signatures(self):
        iso = bytearray(40000)
        iso[0x8001:0x8006] = b"CD001"
        self.assertEqual(self.sniff_bytes(bytes(iso)), "iso9660")

        ext4 = bytearray(4096)
        ext4[1080:1082] = b"\x53\xef"
        ext4[1024 + 0x60] = 0x40                      # extents feature
        self.assertEqual(self.sniff_bytes(bytes(ext4)), "ext4")

        ntfs = bytearray(1024)
        ntfs[3:11] = b"NTFS    "
        self.assertEqual(self.sniff_bytes(bytes(ntfs)), "ntfs")

        self.assertIsNone(self.sniff_bytes(bytes(1024)))


class TestLinuxDryRun(unittest.TestCase):
    def setUp(self):
        self.box, self.session = make_box("linux")

    def test_mount_then_unmount_by_name(self):
        res = self.box.call("mount", {"source": "ubuntu.iso"})
        self.assertTrue(res["ok"], res)
        self.assertEqual(res["loop_device"], "/dev/loop0")
        self.assertEqual(res["filesystem"], "iso9660")
        self.assertEqual(res["mount_point"], "/mnt/agent/ubuntu")
        trace = self.box.runner.take_trace()
        self.assertTrue(any(t.startswith("losetup --find") for t in trace))
        self.assertTrue(any("MS_RDONLY" in t for t in trace))

        res = self.box.call("unmount", {"target": "ubuntu"})
        self.assertTrue(res["ok"], res)
        self.assertEqual(res["released"], "/dev/loop0")
        self.assertEqual(self.session.mounts, [])

    def test_second_mount_gets_unique_path(self):
        self.box.call("mount", {"source": "ubuntu.iso"})
        res = self.box.call("mount", {"source": "ubuntu.iso"})
        self.assertEqual(res["mount_point"], "/mnt/agent/ubuntu-2")

    def test_refuses_system_mount_points(self):
        res = self.box.call("mount", {"source": "ubuntu.iso", "mount_point": "/etc"})
        self.assertFalse(res["ok"])
        self.assertIn("refusing", res["error"])
        self.assertEqual(self.box.runner.take_trace(), [])   # refused before any command ran
        self.assertFalse(self.box.call("unmount", {"target": "/"})["ok"])

    def test_rejects_malformed_tool_calls(self):
        for args in ({}, {"path": "x.iso"}, {"source": "x.iso", "partition": "two"}, "x.iso"):
            res = self.box.call("mount", args)
            self.assertFalse(res["ok"], args)
        self.assertEqual(self.box.runner.take_trace(), [])

    def test_unknown_tool_and_bad_args(self):
        self.assertFalse(self.box.call("rm_rf", {})["ok"])
        self.assertFalse(self.box.call("mount", {"nope": 1})["ok"])

    def test_offline_backend_end_to_end(self):
        calls = []

        def execute(name, args):
            calls.append((name, args))
            return self.box.call(name, args)

        text = OfflineBackend(self.session, "linux").respond("mount ubuntu.iso so I can see inside", execute)
        self.assertEqual([c[0] for c in calls], ["mount", "list_files"])
        self.assertEqual(calls[1][1], {"path": "/mnt/agent/ubuntu"})
        self.assertIn("Mounted ubuntu.iso at /mnt/agent/ubuntu", text)


class TestWindowsDryRun(unittest.TestCase):
    def setUp(self):
        self.box, self.session = make_box("windows")

    def test_iso_gets_drive_letter_and_unmounts(self):
        res = self.box.call("mount", {"source": "ubuntu.iso"})
        self.assertTrue(res["ok"], res)
        self.assertEqual(res["mount_point"], "D:\\")
        self.assertEqual(res["method"], "Mount-DiskImage")
        self.assertTrue(any("Mount-DiskImage" in t for t in self.box.runner.take_trace()))

        images = self.box.call("list_attached_images")["images"]
        self.assertEqual(images[0]["name"], "D:")

        res = self.box.call("unmount", {"target": "D:"})
        self.assertTrue(res["ok"], res)
        self.assertEqual(self.session.mounts, [])

    def test_partition_mount(self):
        res = self.box.call("mount", {"source": "disk1", "partition": 1})
        self.assertTrue(res["ok"], res)
        self.assertEqual(res["mount_point"], "E:\\")
        self.assertTrue(self.box.call("unmount", {"target": "it"})["ok"])

    def test_refusals(self):
        self.assertIn("ext4", self.box.call("mount", {"source": "rootfs.img"})["error"])
        self.assertIn("drive letter", self.box.call("mount", {"source": "a.iso", "mount_point": "/mnt/x"})["error"])
        self.assertIn("Windows itself", self.box.call("unmount", {"target": "C:"})["error"])

    def test_device_tree(self):
        devices = self.box.call("list_block_devices")["devices"]
        self.assertEqual(devices[0]["children"][2]["mountpoint"], "C:\\")


if __name__ == "__main__":
    unittest.main()
