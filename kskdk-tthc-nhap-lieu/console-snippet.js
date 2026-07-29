/**
 * Bookmarklet / Console snippet — chạy khi đang mở form KSKDK_TTHC.
 * Cách dùng: F12 → Console → dán toàn bộ → Enter.
 * Hoặc tạo bookmark với nội dung: javascript:(...) thu gọn.
 */
(function () {
  const clickSave = () => {
    const btns = Array.from(document.querySelectorAll('dx-button, .dx-button, button'));
    const b = btns.find((x) => /^(Lưu|Save)$/i.test((x.innerText || '').trim()) || /(^|\s)Lưu(\s|$)/.test(x.innerText || ''));
    if (b) b.click();
    else alert('Không tìm thấy nút Lưu');
  };
  const onKey = (e) => {
    if (e.ctrlKey && (e.key === 's' || e.key === 'S')) {
      e.preventDefault();
      clickSave();
    }
  };
  document.addEventListener('keydown', onKey, true);
  console.log('%cKSKDK shortcut: Ctrl+S = Lưu', 'color:#0f6a5a;font-weight:bold');
  clickSave;
})();
