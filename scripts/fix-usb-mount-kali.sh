#!/usr/bin/env bash
# Fix USB mount errors on Kali/Debian/Ubuntu
# Error: wrong fs type, bad option, bad superblock, missing codepage or helper program
# Example: Error mounting /dev/sdb1 at /run/media/kali/DỮ LIỆU
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Chạy script với quyền root:"
  echo "  sudo bash $0"
  exit 1
fi

echo "==> Cập nhật danh sách gói..."
apt-get update -y

echo "==> Cài các gói hỗ trợ USB / NTFS / exFAT / FAT..."
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  ntfs-3g \
  exfatprogs \
  exfat-fuse \
  dosfstools \
  mtools \
  udisks2 \
  gvfs \
  gvfs-backends \
  gvfs-fuse \
  fuse3 \
  usbutils \
  parted \
  gparted

# Một số bản Kali cũ vẫn còn tên gói exfat-utils
apt-get install -y exfat-utils 2>/dev/null || true

echo
echo "==> Nạp lại module kernel (nếu có)..."
modprobe fuse 2>/dev/null || true
modprobe usb_storage 2>/dev/null || true
modprobe uas 2>/dev/null || true
modprobe nls_cp437 2>/dev/null || true
modprobe nls_utf8 2>/dev/null || true

echo
echo "==> Thiết bị lưu trữ hiện có:"
lsblk -o NAME,SIZE,FSTYPE,LABEL,MOUNTPOINT,MODEL

echo
echo "==> Chi tiết phân vùng (blkid):"
blkid || true

DEVICE="${1:-}"
if [[ -z "${DEVICE}" ]]; then
  # Gợi ý phân vùng USB phổ biến nhất từ lỗi: /dev/sdb1
  if [[ -b /dev/sdb1 ]]; then
    DEVICE="/dev/sdb1"
  fi
fi

if [[ -n "${DEVICE}" && -b "${DEVICE}" ]]; then
  FSTYPE="$(blkid -o value -s TYPE "${DEVICE}" 2>/dev/null || true)"
  echo
  echo "==> Thử gắn kết ${DEVICE} (FSTYPE=${FSTYPE:-unknown})..."

  case "${FSTYPE}" in
    ntfs|NTFS)
      echo "Phát hiện NTFS — chạy ntfsfix rồi mount bằng ntfs-3g..."
      ntfsfix -b -d "${DEVICE}" || true
      mkdir -p /mnt/usb-data
      if mount -t ntfs-3g -o rw,uid=1000,gid=1000 "${DEVICE}" /mnt/usb-data; then
        echo "OK: đã gắn kết tại /mnt/usb-data"
        df -h /mnt/usb-data
      else
        echo "Mount read-write thất bại, thử read-only..."
        mount -t ntfs-3g -o ro "${DEVICE}" /mnt/usb-data && echo "OK (read-only): /mnt/usb-data"
      fi
      ;;
    exfat|EXFAT)
      echo "Phát hiện exFAT — mount bằng exfat..."
      mkdir -p /mnt/usb-data
      mount -t exfat -o rw,uid=1000,gid=1000 "${DEVICE}" /mnt/usb-data \
        || mount.exfat-fuse "${DEVICE}" /mnt/usb-data
      echo "OK: đã gắn kết tại /mnt/usb-data"
      df -h /mnt/usb-data
      ;;
    vfat|fat|FAT|msdos)
      echo "Phát hiện FAT/vfat..."
      mkdir -p /mnt/usb-data
      mount -t vfat -o rw,uid=1000,gid=1000,utf8=1 "${DEVICE}" /mnt/usb-data
      echo "OK: đã gắn kết tại /mnt/usb-data"
      df -h /mnt/usb-data
      ;;
    "")
      echo "Không nhận diện được filesystem của ${DEVICE}."
      echo "Thử lần lượt:"
      echo "  sudo mount -t ntfs-3g ${DEVICE} /mnt/usb-data"
      echo "  sudo mount -t exfat ${DEVICE} /mnt/usb-data"
      echo "  sudo mount -t vfat ${DEVICE} /mnt/usb-data"
      ;;
    *)
      echo "Filesystem ${FSTYPE} — mount tự động..."
      mkdir -p /mnt/usb-data
      mount "${DEVICE}" /mnt/usb-data
      echo "OK: đã gắn kết tại /mnt/usb-data"
      df -h /mnt/usb-data
      ;;
  esac
else
  echo
  echo "Chưa chỉ định phân vùng. Sau khi cắm USB, chạy lại:"
  echo "  sudo bash $0 /dev/sdb1"
  echo
  echo "Hoặc gắn thủ công:"
  echo "  sudo mkdir -p /mnt/usb-data"
  echo "  sudo ntfsfix -b -d /dev/sdb1          # nếu là NTFS"
  echo "  sudo mount -t ntfs-3g /dev/sdb1 /mnt/usb-data"
fi

echo
echo "Xong. Rút USB khỏi Thunar rồi gắn lại (hoặc mở /mnt/usb-data)."
echo "Nếu vẫn lỗi: mở USB trên Windows → chuột phải ổ đĩa → Properties → Tools → Check,"
echo "hoặc tắt Fast Startup trên Windows rồi rút USB an toàn."
