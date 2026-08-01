# ADMIN

## Sửa lỗi USB trên Kali Linux

Lỗi dạng:

```text
Không thể gắn kết "DỮ LIỆU".
Error mounting /dev/sdb1 ... wrong fs type, bad option, bad superblock
on /dev/sdb1, missing codepage or helper program, or other error.
```

### Cách 1 — Chạy script (khuyến nghị)

Trên máy Kali, mở Terminal và chạy:

```bash
sudo bash scripts/fix-usb-mount-kali.sh
```

Nếu USB là `/dev/sdb1` (như trong thông báo lỗi), chạy:

```bash
sudo bash scripts/fix-usb-mount-kali.sh /dev/sdb1
```

### Cách 2 — Cài gói thủ công

```bash
sudo apt update
sudo apt install -y ntfs-3g exfatprogs exfat-fuse dosfstools mtools udisks2 gvfs gvfs-backends gvfs-fuse fuse3 usbutils
```

Rồi sửa và gắn USB NTFS:

```bash
sudo ntfsfix -b -d /dev/sdb1
sudo mkdir -p /mnt/usb-data
sudo mount -t ntfs-3g -o rw,uid=$(id -u),gid=$(id -g) /dev/sdb1 /mnt/usb-data
```

Sau đó rút USB trong Thunar và cắm lại, hoặc mở thư mục `/mnt/usb-data`.
