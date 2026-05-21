# 漫画生成链路说明

当前 demo 的漫画页是事件改编，不是严格转绘。流程是：视频高光片段 -> 关键帧 -> VLM 识别场景/主体/动作/事件 -> 六格文字分镜 -> 文生图生成整页漫画 -> 本地叠加中文对白。

这个逻辑能验证“高光变成漫画故事”的方向，但不能保证画面忠实，因为文生图会重新想象狗、场景、构图和物体。你说得对，只靠文字描述生图，漫画就可能不反映真实素材。

更适合 AUREN 的产品级链路应该是：

1. 每格先绑定一个 evidence frame 或 1-3 张连续证据帧。
2. 对证据帧做主体/场景 mask：狗、主人、其他狗、推车、草地、室内店铺、围栏等。
3. 用图生图或带结构控制的模型重绘，而不是纯文生图；保留原始构图、主体位置和关键物体。
4. 用同一只宠物的参考图做角色一致性约束，避免每格变成不同的狗。
5. 只把想象元素作为叠加层加入，例如气味轨迹、想法泡泡、小地图符号，而不替换真实事件。
6. 最后本地排版对白和字幕，避免图像模型生成乱码文字。

本次六格绑定的真实证据如下：

- Panel 1｜门开了，我还在认真考虑。｜pov_007_s0002｜C:\Users\maoyihang\AUREN_outputs\AUREN_POV_TEST_002\vlm_jobs_v3\primary_frames\pov_007_s0002_primary.jpg
- Panel 2｜这只白色轮子，值得跟踪。｜pov_001_s0005｜C:\Users\maoyihang\AUREN_outputs\AUREN_POV_TEST_002\vlm_jobs_v3\primary_frames\pov_001_s0005_primary.jpg
- Panel 3｜等一下，你也是出来巡逻的吗？｜pov_001_s0013｜C:\Users\maoyihang\AUREN_outputs\AUREN_POV_TEST_002\vlm_jobs_v3\primary_frames\pov_001_s0013_primary.jpg
- Panel 4｜人类的洞穴，灯很多，味道也很多。｜pov_008_s0010｜C:\Users\maoyihang\AUREN_outputs\AUREN_POV_TEST_002\vlm_jobs_v3\primary_frames\pov_008_s0010_primary.jpg
- Panel 5｜草丛今天留言很多。｜pov_002_s0019｜C:\Users\maoyihang\AUREN_outputs\AUREN_POV_TEST_002\vlm_jobs_v3\primary_frames\pov_002_s0019_primary.jpg
- Panel 6｜围栏后面，一定藏着新地图。｜pov_005_s0011｜C:\Users\maoyihang\AUREN_outputs\AUREN_POV_TEST_002\vlm_jobs_v3\primary_frames\pov_005_s0011_primary.jpg