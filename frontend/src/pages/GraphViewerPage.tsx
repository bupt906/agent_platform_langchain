export default function GraphViewerPage() {
  return (
    <div className="p-6 space-y-4 overflow-y-auto h-full">
      <h2 className="text-lg font-semibold">知识图谱</h2>
      <p className="text-sm text-gray-500">
        Knowledge Graph 抽取完成后，通过 viewer.html 查看交互式图谱。
        当前页面为占位，后续可集成 generate_viewer.py 的输出列表。
      </p>
      <div className="bg-white rounded-xl border border-gray-200 p-8 text-center text-gray-400">
        图谱列表将在后续版本中支持。
        <br />
        现在可以通过对话页使用 knowledge-graph-extraction Skill 生成图谱，
        <br />
        生成后在输出目录中打开 viewer.html 查看。
      </div>
    </div>
  );
}
