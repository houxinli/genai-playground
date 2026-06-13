# 2026-06-13 source adapter 与 bilingual renderer shadow path(P0.5 部分)

## 背景

迁移需要把现有源转成 DocumentRevision,并有一个能复刻现有 bilingual 输出的 renderer
(shadow path,system-design §20 Phase 1)。依赖 P0.3 schema 与 P0.4 fixture/source_identity。

## 改动

- `source_adapter.py`:源目录 → DocumentRevision 列表(枚举 .txt、排除 .meta.json,委托 source_identity)。
- `renderer.py::render_bilingual`:revision + 逐 segment 译文 → bilingual,复刻现有格式——
  front matter 里 title、caption/excerpt(provider 感知)、series.title(缩进层)、tags 的译文行紧跟
  源行插入,其余键透传;正文每个非空源行后紧跟译文,源空行结构原样保留;渲染前按 source_text 校验
  每行与 revision 匹配,行数不符报错。
- golden `*.render.bilingual.txt` + 测试(逐字节匹配、配对、空行保留、缺译文报错、adapter)。

## 决策(已记入 PR)

- 范围收敛:#37 只交付 adapter + bilingual renderer;zh 渲染需复刻 extract_chinese 的字段变换
  (ID 改名、caption HTML 剥离、tags 配对等),自成一摊,拆为 follow-up #42,保持 PR 可评审。
- renderer 以"逐 segment 译文 map"驱动(将来由 DocumentVersion 选定的 candidate 提供);本任务
  不含 candidate/version 模型(P1)。
- shadow 验证用合成 fixture 的 golden:真实语料含成人内容且 git-ignore,不能入库当 golden。

## 验证

pytest 全量 149 绿(基线 142→149);渲染输出与真实 *_bilingual 格式逐字节一致。
