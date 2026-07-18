"use client";

import {
  getCampaigns,
  getMessaging,
  getRevenue,
  type CampaignRoi,
  type MessagingMonth,
  type MessagingPayload,
  type RevenueMonth,
} from "@/lib/api";
import { useApi } from "@/lib/use-api";
import { formatCount, formatINR, formatINRCompact, formatPct, labelize } from "@/lib/format";
import { RepeatRateLine, RevenueStack } from "@/components/charts";
import {
  Card,
  EmptyState,
  ErrorPanel,
  OfflinePanel,
  PageHeader,
  Skeleton,
  StatTile,
} from "@/components/ui";

interface ChannelTotals {
  channel: string;
  sends: number;
  delivered: number;
  opened_or_read: number;
  clicked: number;
  bounced: number;
  attributed_orders: number;
  attributed_revenue_paise: number;
}

/** messaging_facts (tenant x month x channel) rolled up per channel. */
function byChannel(months: MessagingMonth[]): ChannelTotals[] {
  const acc = new Map<string, ChannelTotals>();
  for (const m of months) {
    const t = acc.get(m.channel) ?? {
      channel: m.channel,
      sends: 0,
      delivered: 0,
      opened_or_read: 0,
      clicked: 0,
      bounced: 0,
      attributed_orders: 0,
      attributed_revenue_paise: 0,
    };
    t.sends += m.sends;
    t.delivered += m.delivered;
    t.opened_or_read += m.opened_or_read;
    t.clicked += m.clicked;
    t.bounced += m.bounced;
    t.attributed_orders += m.attributed_orders;
    t.attributed_revenue_paise += m.attributed_revenue_paise;
    acc.set(m.channel, t);
  }
  return [...acc.values()].sort(
    (a, b) => b.attributed_revenue_paise - a.attributed_revenue_paise,
  );
}

function ChannelTable({ rows }: { rows: ChannelTotals[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-line text-left text-xs uppercase tracking-wider text-graphite">
            <th className="py-2 pr-3 font-medium">Channel</th>
            <th className="num py-2 pr-3 text-right font-medium">Sends</th>
            <th className="num py-2 pr-3 text-right font-medium">Delivered</th>
            <th className="num py-2 pr-3 text-right font-medium">Open / read</th>
            <th className="num py-2 pr-3 text-right font-medium">Clicked</th>
            <th className="num py-2 pr-3 text-right font-medium">Bounce</th>
            <th className="num py-2 pr-3 text-right font-medium">Orders</th>
            <th className="num py-2 pr-3 text-right font-medium">Revenue</th>
            <th className="num py-2 text-right font-medium">Rev / msg</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.channel} className="border-b border-line/50">
              <td className="py-2.5 pr-3 text-bone">{labelize(r.channel)}</td>
              <td className="num py-2.5 pr-3 text-right text-muted">
                {formatCount(r.sends)}
              </td>
              <td className="num py-2.5 pr-3 text-right text-muted">
                {r.sends ? formatPct(r.delivered / r.sends) : "—"}
              </td>
              <td className="num py-2.5 pr-3 text-right text-muted">
                {r.delivered ? formatPct(r.opened_or_read / r.delivered) : "—"}
              </td>
              <td className="num py-2.5 pr-3 text-right text-muted">
                {r.delivered ? formatPct(r.clicked / r.delivered) : "—"}
              </td>
              <td className="num py-2.5 pr-3 text-right text-ember">
                {r.sends ? formatPct(r.bounced / r.sends) : "—"}
              </td>
              <td className="num py-2.5 pr-3 text-right">
                {formatCount(r.attributed_orders)}
              </td>
              <td className="num py-2.5 pr-3 text-right text-teal">
                {formatINRCompact(r.attributed_revenue_paise)}
              </td>
              <td className="num py-2.5 text-right">
                {r.sends ? formatINR(r.attributed_revenue_paise / r.sends) : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CampaignTable({ rows }: { rows: CampaignRoi[] }) {
  const sorted = [...rows].sort(
    (a, b) => b.attributed_revenue_paise - a.attributed_revenue_paise,
  );
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-line text-left text-xs uppercase tracking-wider text-graphite">
            <th className="py-2 pr-3 font-medium">Campaign</th>
            <th className="py-2 pr-3 font-medium">Channel</th>
            <th className="num py-2 pr-3 text-right font-medium">Sends</th>
            <th className="num py-2 pr-3 text-right font-medium">Opens</th>
            <th className="num py-2 pr-3 text-right font-medium">Clicks</th>
            <th className="num py-2 pr-3 text-right font-medium">Orders</th>
            <th className="num py-2 pr-3 text-right font-medium">Revenue</th>
            <th className="num py-2 text-right font-medium">Rev / msg</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((c) => (
            <tr key={c.campaign_id} className="border-b border-line/50">
              <td className="max-w-56 truncate py-2.5 pr-3 text-bone" title={c.campaign_name}>
                {c.campaign_name}
              </td>
              <td className="py-2.5 pr-3 text-muted">{labelize(c.channel)}</td>
              <td className="num py-2.5 pr-3 text-right text-muted">{formatCount(c.sends)}</td>
              <td className="num py-2.5 pr-3 text-right text-muted">
                {formatCount(c.unique_opens)}
              </td>
              <td className="num py-2.5 pr-3 text-right text-muted">
                {formatCount(c.unique_clicks)}
              </td>
              <td className="num py-2.5 pr-3 text-right">{formatCount(c.attributed_orders)}</td>
              <td className="num py-2.5 pr-3 text-right text-teal">
                {formatINRCompact(c.attributed_revenue_paise)}
              </td>
              <td className="num py-2.5 text-right">{formatINR(c.revenue_per_message_paise)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function RevenuePage() {
  const { data, loading, offline, error, retry } = useApi<{
    revenue: RevenueMonth[];
    campaigns: CampaignRoi[] | null;
    messaging: MessagingPayload | null;
  }>(async (t) => {
    const [revenue, campaigns, messaging] = await Promise.all([
      getRevenue(t.id),
      getCampaigns(t.id),
      getMessaging(t.id),
    ]);
    return { revenue, campaigns, messaging };
  });

  if (offline) return <OfflinePanel retry={retry} />;
  if (loading) return <Skeleton blocks={3} />;
  if (error === "no tenants")
    return <EmptyState note="No tenants yet — seed the demo tenant first." />;
  if (error || !data) return <ErrorPanel message={error ?? "no data"} />;

  const { revenue, campaigns, messaging } = data;
  const channels = messaging ? byChannel(messaging.months) : null;
  const wa = messaging?.whatsapp_summary ?? null;
  const totals = revenue.reduce(
    (acc, m) => ({
      revenue: acc.revenue + m.revenue_paise,
      repeat: acc.repeat + m.repeat_revenue_paise,
    }),
    { revenue: 0, repeat: 0 },
  );

  return (
    <>
      <PageHeader
        title="Revenue"
        sub={
          revenue.length
            ? `${formatINRCompact(totals.revenue)} total · ${formatPct(
                totals.revenue ? totals.repeat / totals.revenue : 0,
              )} from repeat orders`
            : undefined
        }
      />
      <Card title="Monthly revenue — new vs repeat">
        {revenue.length ? (
          <>
            <RevenueStack data={revenue} />
            <div className="mt-3 flex gap-5 text-xs text-muted">
              <span className="flex items-center gap-1.5">
                <span className="inline-block h-2.5 w-2.5 rounded-[2px] bg-teal" /> Repeat
              </span>
              <span className="flex items-center gap-1.5">
                <span className="inline-block h-2.5 w-2.5 rounded-[2px] bg-series-new" /> New
              </span>
            </div>
          </>
        ) : (
          <EmptyState note="No revenue history yet — run the nightly pipeline." />
        )}
      </Card>
      {revenue.length > 0 && (
        <Card title="Repeat rate by month" className="mt-4">
          <RepeatRateLine data={revenue} />
        </Card>
      )}
      <Card title="Channels — email vs WhatsApp" className="mt-4">
        {channels === null ? (
          <EmptyState note="Messaging endpoint not available on this API build." />
        ) : channels.length === 0 ? (
          <EmptyState note="No messaging activity yet." />
        ) : (
          <>
            {wa && (
              <div className="mb-4 grid grid-cols-2 gap-4 md:grid-cols-4">
                <StatTile
                  label="Rev / conversation"
                  value={formatINR(wa.revenue_per_conversation_paise)}
                  tone="warn"
                  sub="WhatsApp · trailing 12mo · Bet 6"
                />
                <StatTile
                  label="WhatsApp revenue"
                  value={formatINRCompact(wa.attributed_revenue_paise)}
                  sub={`${formatCount(wa.sends)} conversations`}
                />
                <StatTile label="Read rate" value={formatPct(wa.read_rate)} />
                <StatTile label="Reply rate" value={formatPct(wa.reply_rate)} />
              </div>
            )}
            <ChannelTable rows={channels} />
          </>
        )}
      </Card>
      <Card title="Campaign ROI" className="mt-4">
        {campaigns === null ? (
          <EmptyState note="Campaign ROI endpoint not available on this API build." />
        ) : campaigns.length ? (
          <CampaignTable rows={campaigns} />
        ) : (
          <EmptyState note="No campaigns attributed yet." />
        )}
      </Card>
    </>
  );
}
