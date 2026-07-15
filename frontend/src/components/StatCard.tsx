interface StatCardProps {
  title: string;
  value: string;
  subtitle?: string;
  color?: string;
}

export default function StatCard({ title, value, subtitle, color = "text-blue-600" }: StatCardProps) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <p className="text-sm text-gray-500 mb-1">{title}</p>
      <p className={`text-2xl font-bold ${color}`}>{value}</p>
      {subtitle && <p className="text-xs text-gray-400 mt-1">{subtitle}</p>}
    </div>
  );
}
