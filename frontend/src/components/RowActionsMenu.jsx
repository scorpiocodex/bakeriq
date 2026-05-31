import { useEffect, useRef, useState } from 'react';
import { MoreHorizontal } from 'lucide-react';

/**
 * Compact "⋯" trigger that opens a small popover menu of row actions.
 *
 * actions: [{ label, onClick, destructive?: boolean, disabled?: boolean }]
 *
 * The popover uses `position: fixed` with coordinates derived from the
 * trigger button's bounding rect. This escapes parent `overflow-hidden`
 * containers (e.g., the table wrapper with rounded corners) that would
 * otherwise clip the menu — important for rows near the bottom of short
 * lists, like a single inactive customer.
 *
 * Closes on outside-click and Escape.
 */
export default function RowActionsMenu({ actions }) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState({ top: 0, right: 0 });
  const triggerRef = useRef(null);
  const menuRef = useRef(null);

  // Compute popover position from the trigger's bounding rect when opening.
  function openMenu() {
    const btn = triggerRef.current;
    if (!btn) return;
    const r = btn.getBoundingClientRect();
    setPos({
      top: r.bottom + 4, // 4px gap below the button
      right: window.innerWidth - r.right, // align right edge to button
    });
    setOpen(true);
  }

  // Close on outside-click and Escape
  useEffect(() => {
    if (!open) return;
    function onClick(e) {
      if (
        menuRef.current &&
        !menuRef.current.contains(e.target) &&
        triggerRef.current &&
        !triggerRef.current.contains(e.target)
      ) {
        setOpen(false);
      }
    }
    function onKey(e) {
      if (e.key === 'Escape') setOpen(false);
    }
    document.addEventListener('mousedown', onClick);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onClick);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  // Re-close on scroll/resize — the fixed-position menu would otherwise
  // float away from its trigger
  useEffect(() => {
    if (!open) return;
    function close() {
      setOpen(false);
    }
    window.addEventListener('scroll', close, true);
    window.addEventListener('resize', close);
    return () => {
      window.removeEventListener('scroll', close, true);
      window.removeEventListener('resize', close);
    };
  }, [open]);

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          if (open) setOpen(false);
          else openMenu();
        }}
        className="p-1 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded-md"
        aria-label="Row actions"
        aria-haspopup="menu"
        aria-expanded={open}
      >
        <MoreHorizontal size={16} />
      </button>

      {open && (
        <div
          ref={menuRef}
          role="menu"
          style={{ top: pos.top, right: pos.right }}
          className="fixed z-50 min-w-[140px] bg-white border border-slate-200 rounded-md shadow-md py-1"
        >
          {actions.map((a, i) => (
            <button
              key={i}
              type="button"
              role="menuitem"
              disabled={a.disabled}
              onClick={(e) => {
                e.stopPropagation();
                setOpen(false);
                a.onClick();
              }}
              className={`block w-full text-left px-3 py-1.5 text-xs disabled:opacity-50 ${
                a.destructive ? 'text-red-600 hover:bg-red-50' : 'text-slate-700 hover:bg-slate-50'
              }`}
            >
              {a.label}
            </button>
          ))}
        </div>
      )}
    </>
  );
}
