import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { api, ApiError } from "../lib/api";
import { formatINR } from "../lib/format";

const W = 760;
const H = 240;

export default function PortfolioPage() {
  const occupancy = useQuery({ queryKey: ["portfolio-occupancy"], queryFn: api.occupancy });
  const revenue = useQuery({ queryKey: ["portfolio-revenue"], queryFn: api.revenue });
  const efficiency = useQuery({ queryKey: ["portfolio-efficiency"], queryFn: api.collectionEfficiency });
  const [sort, setSort] = useState(true);
  const points = efficiency.data?.months ?? [];
  const line = useMemo(() => {
    const left = 42, right = 12, top = 20, bottom = 34;
    const x = (i: number) => left + i * (W - left - right) / Math.max(1, points.length - 1);
    const y = (v: number) => top + (1 - Math.min(1.15, v) / 1.15) * (H - top - bottom);
    return { x, y, d: points.map((p: any, i: number) => `${i ? "L" : "M"} ${x(i)} ${y(p.share)}`).join(" ") };
  }, [points]);
  const vacant = occupancy.data?.vacant_units ?? [];
  const sortedVacant = [...vacant].sort((a: any, b: any) => sort ? b.days_vacant - a.days_vacant : a.days_vacant - b.days_vacant);
  const errors = [occupancy.error, revenue.error, efficiency.error].filter(Boolean);
  return <>
    <h1 className="page-title">Portfolio</h1>
    {(occupancy.isLoading || revenue.isLoading || efficiency.isLoading) && <p className="state-line">Loading portfolio data…</p>}
    {errors.map((error: any, i) => <p className="state-line" key={i}>Could not load portfolio data. {error instanceof ApiError ? error.message : "Check the API and try again."}</p>)}
    {occupancy.data && <>
      <p>{occupancy.data.total.occupied} of {occupancy.data.total.units} units are occupied across {occupancy.data.properties.length} properties{revenue.data ? `; ${formatINR(revenue.data.months.at(-1)?.collected ?? 0)} was collected in the latest cycle.` : "."}</p>
      <h2 className="subhead">Occupancy</h2>
      <div className="portfolio-rows">
        {occupancy.data.properties.map((p: any) => <div className="portfolio-row" key={p.property_id}>
          <span>{p.property}</span><svg viewBox="0 0 200 18" role="img" aria-label={`${Math.round(p.occupancy_rate * 100)} percent occupied`}><path d={`M 2 9 Q 48 ${8 + (p.property_id % 3)} 100 9 T ${2 + 196 * p.occupancy_rate} 9`} fill="none" stroke="var(--indigo)" strokeWidth="5" strokeLinecap="round" /></svg>
          <span>{p.occupied} of {p.units} units occupied</span>
        </div>)}
      </div>
      <p className="small soft">Total: {occupancy.data.total.occupied} of {occupancy.data.total.units} units occupied.</p>
    </>}
    {efficiency.data && <>
      <hr className="rule"/><h2 className="subhead">Collection efficiency</h2>
      <p>Share of billed rent collected by five days after the due date. Cynbit’s target is 100 percent.</p>
      <svg className="chart-svg" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Monthly collection efficiency">
        <defs><pattern id="portfolio-hatch" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="8" stroke="var(--indigo-soft)" strokeWidth="1"/></pattern></defs>
        {[0, .5, 1].map(v => <g key={v}><line x1="42" x2={W-12} y1={line.y(v)} y2={line.y(v)} stroke={v === 1 ? "var(--indigo)" : "var(--rule)"} strokeDasharray={v === 1 ? "6 4" : undefined}/><text x="36" y={line.y(v)+4} textAnchor="end" fill="var(--indigo-soft)" style={{fontSize:12,fontFamily:"var(--font-body)"}}>{v * 100}%</text></g>)}
        <text x={W-12} y={line.y(1)-6} textAnchor="end" fill="var(--indigo)" style={{fontSize:12,fontFamily:"var(--font-body)"}}>Target 100 percent</text>
        <path d={line.d} fill="none" stroke="var(--verdigris)" strokeWidth="2.5"/>
        {points.length > 0 && <path d={`M ${line.x(points.length-1)} ${line.y(points[points.length-1].share)} L ${line.x(points.length)} ${line.y(efficiency.data.forecast.share)}`} fill="none" stroke="url(#portfolio-hatch)" strokeWidth="7"/>}
        <text x="42" y={H-8} fill="var(--indigo-soft)" style={{fontSize:12,fontFamily:"var(--font-body)"}}>24 monthly cycles</text>
      </svg>
      <p>{Math.round(efficiency.data.forecast.share*100)} percent forecast within five days for the open cycle, based on expected on-time share from the risk model.</p>
      <table className="data"><caption className="small soft">Monthly collection efficiency, including the open-cycle forecast.</caption><thead><tr><th>Cycle</th><th>Billed</th><th>Within five days</th><th>Share</th></tr></thead><tbody>{points.map((p:any)=><tr key={p.cycle_month}><td>{p.cycle_month.slice(0,7)}</td><td>{formatINR(p.billed)}</td><td>{formatINR(p.within_grace)}</td><td>{Math.round(p.share*100)}%</td></tr>)}<tr><td>{efficiency.data.forecast.cycle_month.slice(0,7)} forecast</td><td>{formatINR(efficiency.data.forecast.billed)}</td><td>{formatINR(efficiency.data.forecast.expected_within_grace)}</td><td>{Math.round(efficiency.data.forecast.share*100)}%</td></tr></tbody></table>
    </>}
    {revenue.data && <><hr className="rule"/><h2 className="subhead">Revenue</h2><svg className="chart-svg" viewBox={`0 0 ${W} 160`} role="img" aria-label="Billed and collected rent by month">
      {revenue.data.months.map((m:any,i:number)=>{const x=28+i*(W-44)/Math.max(1,revenue.data.months.length-1);const scale=110/Math.max(1,...revenue.data.months.map((q:any)=>q.billed));return <g key={m.cycle_month}><path d={`M ${x-2} 140 L ${x-2} ${140-m.billed*scale}`} stroke="var(--indigo)" strokeWidth="3"/><path d={`M ${x+2} 140 L ${x+2} ${140-m.collected*scale}`} stroke="var(--verdigris)" strokeWidth="3"/></g>})}
      <text x="28" y="15" fill="var(--indigo)" style={{fontSize:12,fontFamily:"var(--font-body)"}}>Billed</text><text x="82" y="15" fill="var(--verdigris)" style={{fontSize:12,fontFamily:"var(--font-body)"}}>Collected</text>
    </svg>
    <table className="data"><caption className="small soft">Monthly billed and collected rent.</caption><thead><tr><th>Cycle</th><th>Billed</th><th>Collected</th><th>Within five days</th></tr></thead><tbody>{revenue.data.months.map((m:any)=><tr key={m.cycle_month}><td>{m.cycle_month.slice(0,7)}</td><td>{formatINR(m.billed)}</td><td>{formatINR(m.collected)}</td><td>{formatINR(m.within_grace)}</td></tr>)}</tbody></table></>}
    <hr className="rule"/><h2 className="subhead">Vacant units</h2>
    {!occupancy.isLoading && vacant.length === 0 && <p className="state-line">No units are vacant. Check back after a lease ends.</p>}
    {vacant.length > 0 && <div className="portfolio-table-wrap"><table className="data"><thead><tr><th>Unit</th><th>Property</th><th>BHK</th><th>Rent</th><th><button className="text-button" onClick={()=>setSort(!sort)}>Days vacant {sort ? "↓" : "↑"}</button></th></tr></thead><tbody>{sortedVacant.map((u:any)=><tr key={u.unit}><td>{u.unit}</td><td>{u.property}</td><td>{u.bhk}</td><td>{formatINR(u.rent_inr)}</td><td>{u.days_vacant}</td></tr>)}</tbody></table></div>}
  </>;
}
