/** Register tabs: the index tabs of a physical register, hanging off the right
 *  edge of the sheet on wide screens and collapsing to a select on narrow
 *  ones. */

interface RegisterItem {
  id: string;
  label: string;
}

interface RegisterTabsProps {
  items: RegisterItem[];
  activeId: string;
  onChange: (id: string) => void;
  ariaLabel: string;
}

export default function RegisterTabs({ items, activeId, onChange, ariaLabel }: RegisterTabsProps) {
  return (
    <>
      <div className="register-tabs" role="tablist" aria-label={ariaLabel}>
        {items.map((item) => (
          <button
            key={item.id}
            role="tab"
            aria-selected={item.id === activeId}
            className="register-tab"
            onClick={() => onChange(item.id)}
          >
            {item.label}
          </button>
        ))}
      </div>
      <select
        className="register-select"
        aria-label={ariaLabel}
        value={activeId}
        onChange={(e) => onChange(e.target.value)}
      >
        {items.map((item) => (
          <option key={item.id} value={item.id}>
            {item.label}
          </option>
        ))}
      </select>
    </>
  );
}
