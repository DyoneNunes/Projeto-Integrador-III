"use client";

import { useState } from "react";
import {
  FileBarChart,
  X,
  Loader2,
  Download,
  Calendar,
  FileText,
} from "lucide-react";
import { jsPDF } from "jspdf";
import autoTable from "jspdf-autotable";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";

interface ByTenant {
  tenant_id: string;
  tenant_name: string;
  total_bytes: number;
  allocations: number;
}

interface ByMonth {
  month: string;
  total_bytes: number;
  allocations: number;
}

interface Allocation {
  allocation_id: string;
  tenant_name: string;
  size_bytes: number;
  shm_key: string;
  state: string;
  created_at: string;
}

interface ReportData {
  period: { from: string; to: string };
  totals: { total_bytes: number; allocations: number };
  by_tenant: ByTenant[];
  by_month: ByMonth[];
  allocations: Allocation[];
}

const COLORS = ["#a78bfa", "#818cf8", "#6366f1", "#4f46e5", "#4338ca"];

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`;
}

function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}

function firstOfMonthISO(): string {
  const d = new Date();
  return new Date(d.getFullYear(), d.getMonth(), 1)
    .toLocaleDateString("en-CA"); // YYYY-MM-DD em horário local
}

function MonthTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const data = payload[0].payload;
  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 shadow-xl">
      <p className="text-sm font-medium text-white">{data.month}</p>
      <p className="text-xs text-violet-400">{formatBytes(data.total_bytes)}</p>
      <p className="text-xs text-gray-400">{data.allocations} alocações</p>
    </div>
  );
}

export default function ReportModal() {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [from, setFrom] = useState(firstOfMonthISO());
  const [to, setTo] = useState(todayISO());
  const [report, setReport] = useState<ReportData | null>(null);
  const [error, setError] = useState<string | null>(null);

  function setQuickRange(months: number) {
    const now = new Date();
    const start = new Date(now.getFullYear(), now.getMonth() - months, 1);
    setFrom(start.toLocaleDateString("en-CA"));
    setTo(todayISO());
  }

  async function generate() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/report?from=${from}&to=${to}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Falha ao gerar relatório");
      setReport(data as ReportData);
    } catch (err: any) {
      setError(err.message || "Falha ao gerar relatório");
      setReport(null);
    } finally {
      setLoading(false);
    }
  }

  function exportCsv() {
    if (!report) return;
    const lines: string[] = [];
    lines.push(`Relatório de Consumo de Memória`);
    lines.push(`Período;${from};${to}`);
    lines.push(
      `Total alocado;${report.totals.total_bytes} bytes;${formatBytes(
        report.totals.total_bytes
      )}`
    );
    lines.push(`Total de alocações;${report.totals.allocations}`);
    lines.push("");
    lines.push("Por Tenant");
    lines.push("Tenant;Bytes;Tamanho;Alocações");
    report.by_tenant.forEach((t) =>
      lines.push(
        `${t.tenant_name};${t.total_bytes};${formatBytes(t.total_bytes)};${t.allocations}`
      )
    );
    lines.push("");
    lines.push("Por Mês");
    lines.push("Mês;Bytes;Tamanho;Alocações");
    report.by_month.forEach((m) =>
      lines.push(
        `${m.month};${m.total_bytes};${formatBytes(m.total_bytes)};${m.allocations}`
      )
    );

    const blob = new Blob([lines.join("\n")], {
      type: "text/csv;charset=utf-8;",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `relatorio-consumo_${from}_a_${to}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  function fmtDate(iso: string): string {
    if (!iso) return "—";
    return new Date(iso).toLocaleString("pt-BR", {
      timeZone: "America/Sao_Paulo",
    });
  }

  function exportPdf() {
    if (!report) return;
    const doc = new jsPDF({ unit: "pt", format: "a4" });
    const marginX = 40;

    // Cabeçalho
    doc.setFontSize(16);
    doc.text("Relatório de Consumo de Memória — MaaS", marginX, 50);
    doc.setFontSize(10);
    doc.setTextColor(110);
    doc.text(`Período: ${from} até ${to}`, marginX, 68);
    doc.text(
      `Total alocado: ${formatBytes(report.totals.total_bytes)}  •  ` +
        `${report.totals.allocations} alocações`,
      marginX,
      82
    );
    doc.setTextColor(0);

    // Tabela: Consumo por tenant
    autoTable(doc, {
      startY: 100,
      head: [["Tenant", "Total alocado", "Alocações"]],
      body: report.by_tenant.map((t) => [
        t.tenant_name,
        formatBytes(t.total_bytes),
        String(t.allocations),
      ]),
      headStyles: { fillColor: [124, 58, 237] }, // violet-600
      styles: { fontSize: 9 },
      margin: { left: marginX, right: marginX },
    });

    // Tabela: Por mês
    const afterTenant = (doc as any).lastAutoTable?.finalY ?? 100;
    autoTable(doc, {
      startY: afterTenant + 20,
      head: [["Mês", "Total alocado", "Alocações"]],
      body: report.by_month.map((m) => [
        m.month,
        formatBytes(m.total_bytes),
        String(m.allocations),
      ]),
      headStyles: { fillColor: [99, 102, 241] }, // indigo
      styles: { fontSize: 9 },
      margin: { left: marginX, right: marginX },
    });

    // Tabela: Alocações detalhadas
    const afterMonth = (doc as any).lastAutoTable?.finalY ?? 100;
    autoTable(doc, {
      startY: afterMonth + 20,
      head: [["ID", "Tenant", "Tamanho", "Estado", "Criado em"]],
      body: report.allocations.map((a) => [
        a.allocation_id.slice(0, 8),
        a.tenant_name,
        formatBytes(a.size_bytes),
        a.state,
        fmtDate(a.created_at),
      ]),
      headStyles: { fillColor: [55, 65, 81] }, // gray-700
      styles: { fontSize: 8 },
      margin: { left: marginX, right: marginX },
    });

    doc.save(`relatorio-alocacoes_${from}_a_${to}.pdf`);
  }

  return (
    <>
      {/* Trigger Button */}
      <button
        onClick={() => setOpen(true)}
        className="flex items-center gap-2 px-4 py-2 bg-gray-800 hover:bg-gray-700 border border-gray-700 text-white text-sm font-medium rounded-lg transition-colors"
      >
        <FileBarChart className="h-4 w-4 text-violet-400" />
        Relatório
      </button>

      {/* Modal Overlay */}
      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={() => setOpen(false)}
          />
          <div className="relative bg-gray-900 border border-gray-700 rounded-2xl shadow-2xl w-full max-w-2xl mx-4 p-6 max-h-[90vh] overflow-y-auto">
            {/* Header */}
            <div className="flex items-center justify-between mb-6">
              <div className="flex items-center gap-2">
                <FileBarChart className="h-5 w-5 text-violet-400" />
                <h3 className="text-lg font-semibold text-white">
                  Relatório de Consumo Mensal
                </h3>
              </div>
              <button
                onClick={() => setOpen(false)}
                className="text-gray-400 hover:text-white transition-colors"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {/* Filtros de período */}
            <div className="flex flex-wrap items-end gap-3 mb-4">
              <div>
                <label className="block text-xs font-medium text-gray-400 mb-1.5">
                  De
                </label>
                <input
                  type="date"
                  value={from}
                  max={to}
                  onChange={(e) => setFrom(e.target.value)}
                  className="px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-violet-500"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-400 mb-1.5">
                  Até
                </label>
                <input
                  type="date"
                  value={to}
                  min={from}
                  max={todayISO()}
                  onChange={(e) => setTo(e.target.value)}
                  className="px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-violet-500"
                />
              </div>
              <button
                onClick={generate}
                disabled={loading}
                className="flex items-center gap-2 px-4 py-2 bg-violet-600 hover:bg-violet-500 disabled:bg-violet-800 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors"
              >
                {loading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Calendar className="h-4 w-4" />
                )}
                Gerar
              </button>
            </div>

            {/* Atalhos rápidos */}
            <div className="flex flex-wrap gap-2 mb-5">
              <button
                onClick={() => setQuickRange(0)}
                className="px-3 py-1 text-xs bg-gray-800 hover:bg-gray-700 border border-gray-700 rounded-full text-gray-300 transition-colors"
              >
                Este mês
              </button>
              <button
                onClick={() => setQuickRange(2)}
                className="px-3 py-1 text-xs bg-gray-800 hover:bg-gray-700 border border-gray-700 rounded-full text-gray-300 transition-colors"
              >
                Últimos 3 meses
              </button>
              <button
                onClick={() => setQuickRange(5)}
                className="px-3 py-1 text-xs bg-gray-800 hover:bg-gray-700 border border-gray-700 rounded-full text-gray-300 transition-colors"
              >
                Últimos 6 meses
              </button>
            </div>

            {error && (
              <div className="mb-4 px-4 py-3 rounded-lg bg-red-950 border border-red-800 text-red-200 text-sm">
                {error}
              </div>
            )}

            {/* Resultado */}
            {report && (
              <div className="space-y-5">
                {/* Cards de resumo */}
                <div className="grid grid-cols-2 gap-3">
                  <div className="bg-gray-800/50 border border-gray-700/50 rounded-lg p-4">
                    <p className="text-xs text-gray-400 mb-1">
                      Total alocado no período
                    </p>
                    <p className="text-2xl font-bold text-white">
                      {formatBytes(report.totals.total_bytes)}
                    </p>
                  </div>
                  <div className="bg-gray-800/50 border border-gray-700/50 rounded-lg p-4">
                    <p className="text-xs text-gray-400 mb-1">
                      Nº de alocações
                    </p>
                    <p className="text-2xl font-bold text-white">
                      {report.totals.allocations}
                    </p>
                  </div>
                </div>

                {report.totals.allocations === 0 ? (
                  <div className="text-center text-gray-600 text-sm py-8">
                    Nenhuma alocação encontrada no período selecionado.
                  </div>
                ) : (
                  <>
                    {/* Gráfico de evolução mensal */}
                    <div>
                      <h4 className="text-sm font-semibold text-gray-300 mb-3">
                        Evolução mês a mês
                      </h4>
                      <ResponsiveContainer width="100%" height={200}>
                        <BarChart
                          data={report.by_month}
                          margin={{ top: 0, right: 10, bottom: 0, left: 0 }}
                        >
                          <XAxis
                            dataKey="month"
                            tick={{ fill: "#9ca3af", fontSize: 11 }}
                            axisLine={false}
                            tickLine={false}
                          />
                          <YAxis
                            tickFormatter={formatBytes}
                            tick={{ fill: "#6b7280", fontSize: 11 }}
                            axisLine={false}
                            tickLine={false}
                            width={70}
                          />
                          <Tooltip
                            content={<MonthTooltip />}
                            cursor={{ fill: "rgba(255,255,255,0.03)" }}
                          />
                          <Bar dataKey="total_bytes" radius={[6, 6, 0, 0]} barSize={36}>
                            {report.by_month.map((_, i) => (
                              <Cell key={i} fill={COLORS[i % COLORS.length]} />
                            ))}
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    </div>

                    {/* Tabela por tenant */}
                    <div>
                      <h4 className="text-sm font-semibold text-gray-300 mb-3">
                        Consumo por tenant
                      </h4>
                      <div className="overflow-x-auto rounded-lg border border-gray-800">
                        <table className="w-full text-sm">
                          <thead>
                            <tr className="border-b border-gray-800 text-gray-400">
                              <th className="text-left px-4 py-2.5 font-medium">
                                Tenant
                              </th>
                              <th className="text-right px-4 py-2.5 font-medium">
                                Total alocado
                              </th>
                              <th className="text-right px-4 py-2.5 font-medium">
                                Alocações
                              </th>
                            </tr>
                          </thead>
                          <tbody>
                            {report.by_tenant.map((t) => (
                              <tr
                                key={t.tenant_id}
                                className="border-b border-gray-800/50 hover:bg-gray-800/30 transition-colors"
                              >
                                <td className="px-4 py-2.5 text-white">
                                  {t.tenant_name}
                                </td>
                                <td className="px-4 py-2.5 text-right text-gray-300">
                                  {formatBytes(t.total_bytes)}
                                </td>
                                <td className="px-4 py-2.5 text-right text-gray-400">
                                  {t.allocations}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </>
                )}

                {/* Exportar */}
                <div className="flex justify-end gap-3">
                  <button
                    onClick={exportPdf}
                    disabled={report.totals.allocations === 0}
                    className="flex items-center gap-2 px-4 py-2 bg-red-600 hover:bg-red-500 disabled:bg-red-900 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors"
                  >
                    <FileText className="h-4 w-4" />
                    Baixar PDF
                  </button>
                  <button
                    onClick={exportCsv}
                    disabled={report.totals.allocations === 0}
                    className="flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:bg-emerald-900 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors"
                  >
                    <Download className="h-4 w-4" />
                    Exportar CSV
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
