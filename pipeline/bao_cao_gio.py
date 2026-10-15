#!/usr/bin/env python3
"""Báo cáo mỗi giờ (tiếng Việt có dấu) trên G:\\Drive của tôi\\BAO_CAO_GIO.

Ghi file .txt nhẹ sau mỗi lần bot chạy: file đã quét / điền / di chuyển.
Không ghi Excel nặng lên G: (tránh treo Drive).
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Thư mục báo cáo trên Google Drive (may A)
G_BAO_CAO_VARIANTS = (
    Path(r"G:/Drive của tôi/BAO_CAO_GIO"),
    Path(r"G:/Drive cua toi/BAO_CAO_GIO"),
    Path(r"G:/My Drive/BAO_CAO_GIO"),
)

# Giải thích ngắn tag di chuyển (tiếng Việt có dấu)
TAG_VI = {
    "PROCESSED": "Đã điền đủ cả 2 tài khoản → chuyển vào PROCESSED",
    "UNDER18": "Bệnh nhân dưới 18 tuổi → chuyển vào UNDER 18",
    "TK1": "Chỉ khớp / điền tài khoản TK1 (pkdkthuankieu) → chuyển vào TK1",
    "TK2": "Chỉ khớp / điền tài khoản TK2 (pkdk_Thuankieu) → chuyển vào TK2",
    "ERROR": "Điền thiếu / mẫu không đủ → chuyển vào ERROR",
    "CCCD": "Trùng CCCD nhưng lệch tên → chuyển vào CCCD (cần xem lại)",
    "NO_TTHC": "Chưa tìm thấy tờ khai trên Medinet → chuyển vào MISSING",
    "REVIEW_U18": "Lỗi đọc PDF / thiếu năm sinh → gửi UNDER 18 để xem lại",
    "PROCESSED_MOVE_FAIL": "Muốn chuyển PROCESSED nhưng thất bại (Drive/file khóa)",
    "ERROR_MOVE_FAIL": "Muốn chuyển ERROR nhưng thất bại",
    "TK1_MOVE_FAIL": "Muốn chuyển TK1 nhưng thất bại",
    "TK2_MOVE_FAIL": "Muốn chuyển TK2 nhưng thất bại",
    "UNDER18_MOVE_FAIL": "Muốn chuyển UNDER 18 nhưng thất bại",
    "CCCD_MOVE_FAIL": "Muốn chuyển CCCD nhưng thất bại",
}

BOT_VI = {
    "inbox": "Bot INBOX — quét thư mục INBOX_CLS (+ ERROR) trên đĩa",
    "missing": "Bot MISSING — rematch qua bảng cases.csv (không rglob cả folder MISSING)",
    "all": "Bot ALL — INBOX + rematch MISSING/TK theo cấu hình",
}


def resolve_bao_cao_dir() -> Path:
    """Ưu tiên G:\\Drive của tôi\\BAO_CAO_GIO; fallback thư mục local nếu G: chưa gắn."""
    env = (os.environ.get("PKDK_BAO_CAO_DIR") or "").strip()
    if env:
        p = Path(env)
        p.mkdir(parents=True, exist_ok=True)
        return p
    for pinned in G_BAO_CAO_VARIANTS:
        try:
            parent = pinned.parent
            if parent.exists() and parent.is_dir():
                pinned.mkdir(parents=True, exist_ok=True)
                return pinned
        except Exception:
            continue
    # Dev / G: chưa mount: vẫn ghi local để không mất báo cáo
    local = ROOT / "pipeline" / "work" / "build" / "BAO_CAO_GIO"
    local.mkdir(parents=True, exist_ok=True)
    return local


def _parse_move_line(line: str) -> dict:
    """Parse 'TAG\\tho_ten\\tfile.pdf\\t->\\tDEST/file.pdf'."""
    parts = (line or "").split("\t")
    tag = parts[0].strip() if parts else ""
    ho_ten = parts[1].strip() if len(parts) > 1 else ""
    file_name = parts[2].strip() if len(parts) > 2 else ""
    dest = ""
    if "->" in parts:
        i = parts.index("->")
        if i + 1 < len(parts):
            dest = parts[i + 1].strip()
    elif len(parts) > 4:
        dest = parts[4].strip()
    return {
        "tag": tag,
        "ho_ten": ho_ten,
        "file_name": file_name,
        "dest": dest,
        "giai_thich": TAG_VI.get(tag, f"Di chuyển / xử lý: {tag}"),
    }


def _git_head_short() -> str:
    try:
        import subprocess

        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(ROOT),
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        )
        return (out or "").strip() or "?"
    except Exception:
        return "?"


def build_report_text(
    *,
    mode: str,
    bot_role: str,
    summary: dict,
    moves: list[str],
    results: list[dict] | None,
    counts0: dict | None,
    counts1: dict | None,
    scan_dirs: list[str] | None = None,
    missing_budget: int = 0,
    accounts: list[str] | None = None,
) -> str:
    now = datetime.now()
    stamp_hien = now.strftime("%d/%m/%Y %H:%M:%S")
    d0 = counts0 or {}
    d1 = counts1 or {}
    lines: list[str] = []
    lines.append("=" * 64)
    lines.append("BÁO CÁO GIỜ — PKDK Thuận Kiều (điền CLS Medinet)")
    lines.append("=" * 64)
    lines.append(f"Thời gian: {stamp_hien}")
    lines.append(f"Mã tip (git): {_git_head_short()}")
    lines.append(f"Chế độ chạy: {mode}")
    lines.append(f"Bot: {BOT_VI.get(bot_role, bot_role)}")
    if accounts:
        lines.append(f"Tài khoản Medinet dùng: {', '.join(accounts)}")
    lines.append("")
    lines.append("--- 1) ĐÃ QUÉT GÌ ---")
    if scan_dirs:
        for d in scan_dirs:
            lines.append(f"  • Thư mục/nguồn: {d}")
    else:
        if bot_role == "inbox":
            lines.append("  • Quét đĩa: INBOX_CLS và ERROR (PDF mới).")
            lines.append("  • Không rematch MISSING trong bot này.")
        elif bot_role == "missing":
            lines.append("  • Rematch MISSING / TK1 / TK2 qua file theo dõi cases.csv.")
            lines.append("  • Không liệt kê toàn bộ thư mục MISSING trên Google Drive (tránh treo).")
            lines.append(f"  • Hạn mức rematch MISSING lần này: {missing_budget}")
        else:
            lines.append("  • Theo cấu hình bot all (INBOX + rematch).")
    lines.append("")
    lines.append("--- 2) SỐ LƯỢNG TRƯỚC / SAU (theo bảng theo dõi) ---")
    for key, label in (
        ("inbox", "INBOX_CLS"),
        ("missing", "MISSING"),
        ("error", "ERROR"),
        ("processed", "PROCESSED"),
    ):
        a = int(d0.get(key, 0) or 0)
        b = int(d1.get(key, 0) or 0)
        delta = b - a
        dau = "+" if delta > 0 else ""
        lines.append(f"  • {label}: trước {a} → sau {b} (thay đổi {dau}{delta})")
    lines.append("")
    lines.append("--- 3) TÓM TẮT XỬ LÝ ---")
    imported = int(summary.get("imported", 0) or 0)
    partial = int(summary.get("imported_partial_to_error", 0) or 0)
    waiting = int(summary.get("waiting_admin", 0) or 0)
    moved_miss = int(summary.get("moved_missing", 0) or 0)
    err_imp = int(summary.get("error_import", 0) or 0)
    new_files = int(summary.get("new_files", 0) or 0)
    lines.append(f"  • PDF mới ghi nhận vào bảng: {new_files}")
    lines.append(f"  • Điền CLS thành công (đủ): {imported}")
    lines.append(f"  • Điền thiếu / đưa ERROR: {partial}")
    lines.append(f"  • Lỗi khi điền web: {err_imp}")
    lines.append(f"  • Chưa khớp tờ khai (chờ / MISSING): {waiting}")
    lines.append(f"  • Chuyển sang MISSING trong lần này: {moved_miss}")
    lines.append(f"  • Số dòng kết quả ghi nhận: {int(summary.get('results', 0) or 0)}")
    if summary.get("abort"):
        lines.append(f"  • DỪNG SỚM: {summary.get('abort')}")
    lines.append("")
    lines.append("--- 4) CHI TIẾT DI CHUYỂN FILE ---")
    if not moves:
        lines.append("  (Không có file nào được di chuyển trong lần chạy này.)")
    else:
        lines.append(f"  Tổng số lần di chuyển ghi nhận: {len(moves)}")
        lines.append("")
        for i, raw in enumerate(moves[:2000], 1):
            m = _parse_move_line(raw)
            lines.append(f"  {i}. File: {m['file_name'] or '(không rõ tên)'}")
            if m["ho_ten"]:
                lines.append(f"     Họ tên: {m['ho_ten']}")
            lines.append(f"     Việc làm: {m['giai_thich']}")
            if m["dest"]:
                lines.append(f"     Đến: {m['dest']}")
            lines.append("")
        if len(moves) > 2000:
            lines.append(f"  … còn {len(moves) - 2000} dòng (đã cắt để file nhẹ).")
    lines.append("")
    lines.append("--- 5) CHI TIẾT ĐIỀN WEB (nếu có) ---")
    res = results or []
    if not res:
        lines.append("  (Không có bản ghi điền web trong lần này.)")
    else:
        for i, r in enumerate(res[:500], 1):
            lines.append(
                f"  {i}. {r.get('file_name') or ''} | {r.get('ho_ten') or ''} | "
                f"TK={r.get('tthc_accounts') or ''} | "
                f"trạng thái={r.get('import_status') or ''} | "
                f"pid={r.get('phieukhamId') or ''}"
            )
        if len(res) > 500:
            lines.append(f"  … còn {len(res) - 500} dòng.")
    lines.append("")
    lines.append("--- 6) GIẢI THÍCH NGẮN ---")
    lines.append("  • INBOX_CLS: PDF mới chờ điền.")
    lines.append("  • MISSING: chưa tìm thấy tờ khai trên Medinet (rematch theo danh sách, không quét full Drive).")
    lines.append("  • PROCESSED / TK1 / TK2 / UNDER 18: đã điền xong và chuyển lưu trữ.")
    lines.append("  • ERROR: điền thiếu chỉ số hoặc mẫu không đủ — cần xem lại.")
    lines.append("=" * 64)
    lines.append("File này tự tạo sau mỗi lần chạy giờ. Xem thêm MOI_NHAT.txt trong cùng thư mục.")
    lines.append("")
    return "\n".join(lines)


def write_hourly_report(
    *,
    mode: str,
    bot_role: str = "all",
    summary: dict | None = None,
    moves: list[str] | None = None,
    results: list[dict] | None = None,
    counts0: dict | None = None,
    counts1: dict | None = None,
    scan_dirs: list[str] | None = None,
    missing_budget: int = 0,
    accounts: list[str] | None = None,
) -> list[Path]:
    """Ghi báo cáo tiếng Việt lên G:\\Drive của tôi\\BAO_CAO_GIO. Trả về list path đã ghi."""
    summary = summary or {}
    moves = moves or []
    text = build_report_text(
        mode=mode,
        bot_role=bot_role,
        summary=summary,
        moves=moves,
        results=results,
        counts0=counts0,
        counts1=counts1,
        scan_dirs=scan_dirs,
        missing_budget=missing_budget,
        accounts=accounts,
    )
    dest_dir = resolve_bao_cao_dir()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    role = (bot_role or "all").strip() or "all"
    named = dest_dir / f"Bao_cao_{stamp}_bot-{role}.txt"
    latest_role = dest_dir / f"MOI_NHAT_bot-{role}.txt"
    latest = dest_dir / "MOI_NHAT.txt"
    written: list[Path] = []
    for path in (named, latest_role, latest):
        try:
            path.write_text(text, encoding="utf-8")
            written.append(path)
        except Exception as e:
            print(f"WARN bao_cao_gio: khong ghi duoc {path}: {e}", file=sys.stderr, flush=True)
    # Bản sao local nếu đang ghi lên G: (phòng Drive sync lỗi)
    try:
        if written and not str(dest_dir).replace("\\", "/").lower().endswith(
            "pipeline/work/build/bao_cao_gio"
        ):
            local = ROOT / "pipeline" / "work" / "build" / "BAO_CAO_GIO"
            local.mkdir(parents=True, exist_ok=True)
            (local / named.name).write_text(text, encoding="utf-8")
            (local / "MOI_NHAT.txt").write_text(text, encoding="utf-8")
    except Exception:
        pass
    return written


if __name__ == "__main__":
    # Smoke: ghi mẫu
    paths = write_hourly_report(
        mode="demo",
        bot_role="inbox",
        summary={"imported": 1, "moved_missing": 0, "results": 1, "new_files": 2},
        moves=["PROCESSED\tNGUYEN VAN A\tmau.pdf\t->\tPROCESSED/mau.pdf"],
        results=[
            {
                "file_name": "mau.pdf",
                "ho_ten": "NGUYEN VAN A",
                "tthc_accounts": "TK1",
                "import_status": "IMPORTED",
                "phieukhamId": "1",
            }
        ],
        counts0={"inbox": 5, "missing": 10, "error": 1, "processed": 100},
        counts1={"inbox": 3, "missing": 10, "error": 1, "processed": 102},
        accounts=["pkdkthuankieu"],
    )
    print("OK", paths)
