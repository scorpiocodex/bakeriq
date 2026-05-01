// Phase 1: static placeholder data. Phase 2 replaces these with API calls
// (useQuery from @tanstack/react-query) hitting /orders/today and friends.
const stats = [
    { label: 'Confirmed', value: '38', delta: '+12 vs yesterday', tone: 'success' },
    { label: 'Pending', value: '3', delta: 'awaiting reply', tone: 'warning' },
    { label: 'Revenue', value: '₹12,450', delta: '+8.2% MoM', tone: 'success' },
    { label: 'Skipped', value: '2', delta: 'customers today', tone: 'neutral' },
];

const channelBreakdown = [
    { label: 'WhatsApp', count: 28, color: 'bg-teal-600' },
    { label: 'Voice bot', count: 8, color: 'bg-brand-600' },
    { label: 'Manual', count: 2, color: 'bg-slate-400' },
];

const lowStock = [
    { name: 'Ghee', current: '2 kg', threshold: '5 kg' },
    { name: 'Cardamom', current: '120 g', threshold: '250 g' },
];

const orderBoard = {
    pending: [
        { customer: 'Suresh K.', detail: 'No reply yet' },
        { customer: 'Priya R.', detail: 'Awaiting confirm' },
    ],
    confirmed: [
        { customer: 'Anita Menon', detail: '10 puffs · 5 ladoo' },
        { customer: 'Ravi S.', detail: '8 puffs · 1 cake' },
    ],
};

function StatCard({ label, value, delta, tone }) {
    const valueColor = tone === 'warning' ? 'text-amber-700' : 'text-slate-900';
    const deltaColor = tone === 'success' ? 'text-green-600' : 'text-slate-500';
    return (
        <div className="bg-white border border-slate-200 rounded-lg p-3">
            <p className="text-[10px] text-slate-500 uppercase tracking-wide font-medium">{label}</p>
            <p className={`text-lg font-medium mt-1 ${valueColor}`}>{value}</p>
            <p className={`text-[10px] mt-1 ${deltaColor}`}>{delta}</p>
        </div>
    );
}

function ChannelRow({ label, count, color }) {
    return (
        <div className="flex items-center gap-2 text-xs">
            <div className={`w-2 h-2 rounded-sm ${color}`} />
            <span className="flex-1 text-slate-700">{label}</span>
            <span className="text-slate-900 font-medium">{count}</span>
        </div>
    );
}

function OrderCard({ customer, detail, tone }) {
    const styles = {
        pending: 'bg-amber-50 border-amber-200 text-amber-800',
        confirmed: 'bg-green-50 border-green-200 text-green-800',
    }[tone];
    return (
        <div className={`${styles} border rounded-md px-2 py-1.5 mb-1.5 text-xs`}>
            <div className="font-medium text-slate-900">{customer}</div>
            <div>{detail}</div>
        </div>
    );
}

export default function Dashboard() {
    return (
        <div className="space-y-3">
            {/* Stat cards row */}
            <div className="grid grid-cols-4 gap-2">
                {stats.map((s) => (
                    <StatCard key={s.label} {...s} />
                ))}
            </div>

            {/* Channel breakdown + low stock alerts */}
            <div className="grid grid-cols-2 gap-2">
                <div className="bg-white border border-slate-200 rounded-lg p-3">
                    <p className="text-xs font-medium text-slate-900 mb-2">Channel breakdown</p>
                    <div className="space-y-1.5">
                        {channelBreakdown.map((c) => (
                            <ChannelRow key={c.label} {...c} />
                        ))}
                    </div>
                </div>
                <div className="bg-amber-50 border border-amber-200 rounded-lg p-3">
                    <p className="text-xs font-medium text-amber-900 mb-2">
                        Low stock alerts ({lowStock.length})
                    </p>
                    <div className="space-y-1 text-xs">
                        {lowStock.map((m) => (
                            <div key={m.name} className="flex justify-between text-amber-900">
                                <span>{m.name}</span>
                                <span className="font-medium">
                                    {m.current} / {m.threshold}
                                </span>
                            </div>
                        ))}
                    </div>
                </div>
            </div>

            {/* Order board */}
            <div className="bg-white border border-slate-200 rounded-lg p-3">
                <div className="flex items-center justify-between mb-2">
                    <p className="text-xs font-medium text-slate-900">Today's order board</p>
                    <span className="text-[10px] text-slate-500">Updated just now</span>
                </div>
                <div className="grid grid-cols-3 gap-2">
                    <div>
                        <div className="text-[10px] text-amber-700 mb-1 uppercase tracking-wide">
                            Pending · {orderBoard.pending.length}
                        </div>
                        {orderBoard.pending.map((o) => (
                            <OrderCard key={o.customer} {...o} tone="pending" />
                        ))}
                    </div>
                    <div>
                        <div className="text-[10px] text-green-700 mb-1 uppercase tracking-wide">
                            Confirmed · {orderBoard.confirmed.length}
                        </div>
                        {orderBoard.confirmed.map((o) => (
                            <OrderCard key={o.customer} {...o} tone="confirmed" />
                        ))}
                    </div>
                    <div>
                        <div className="text-[10px] text-slate-600 mb-1 uppercase tracking-wide">
                            Exported · 0
                        </div>
                        <div className="bg-slate-50 border border-dashed border-slate-300 rounded-md p-3 text-xs text-slate-400 text-center">
                            Run export at 5:30 AM
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}