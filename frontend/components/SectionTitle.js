import Link from 'next/link';

export default function SectionTitle({ children, moreHref, moreLabel = '전체보기' }) {
  return (
    <div className="sec-head">
      <h2 className="h-sec">{children}</h2>
      {moreHref && <Link href={moreHref}>{moreLabel}</Link>}
    </div>
  );
}
