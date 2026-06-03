/* eslint-disable react/prop-types */
/* eslint-disable react/react-in-jsx-scope */
/**
 * BakeriQ brand Mark
 **/

const SIZES = {
  sm: { box: 'w-9 h-9 rounded-lg', stroke: 2.2, svg: 20 },
  md: { box: 'w-10 h-10 rounded-lg', stroke: 2.2, svg: 22 },
};

export default function BrandMark({ size = 'sm' }) {
  const s = SIZES[size] ?? SIZES.sm;
  return (
    <div className={`${s.box} bg-brand-600 flex items-center justify-center flex-shrink-0`}>
      <svg
        width={s.svg}
        height={s.svg}
        viewBox="0 0 24 24"
        fill="none"
        stroke="white"
        strokeWidth={s.stroke}
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z" />
        <line x1="3" y1="6" x2="21" y2="6" />
        <path d="M16 10a4 4 0 0 1-8 0" />
      </svg>
    </div>
  );
}
