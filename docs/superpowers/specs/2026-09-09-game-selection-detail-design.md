> 状态：implemented（本地验证完成，未发布）
> 日期：2026-09-09
> 范围：顺序逐步选择、未完成选择保留、拼图点击次数及六表导出
> 关联：2026-09-09-patient-training-detail-export-design.md
> 实施基线：当前隔离区未提交改动

# 逐步选择与拼图点击数据契约（已获用户功能确认）

工作区仅 /Users/nick/my_dev/workout/MotionCare/.worktrees/game-difficulty-704；保留本会话全部既有改动，不提交/部署/上传。沿用仓库设计、计划、测试和独立审查约定。

用户确认：颜色/图片顺序每步耗时与对错；单次选择每题耗时与结果；拼图点击次数和每张总有效耗时；顺序题退出/超时已选步骤保留并标未完成。

## 明确契约
- API维持client_session_id + question_results，不改变路由；旧无UUID/active_response_v1兼容及其规范化指纹必须保持原样。新客户端全部发送 capture_version=active_response_v2。
- v2每题保留既有字段，新增 expected_step_count: number|null、selection_steps: array、click_count:number|null。每步固定 step_index、selected_value、expected_value、response_duration_ms、is_correct。后端存 GameQuestionSelectionStep，question外键related_name=selection_steps。Question新增expected_step_count/click_count nullable；v2 capture choice；result_type新增 interrupted。is_correct沿用bool，interrupted必须false，导出不把它展示成已作答错误。
- 颜色/图片顺序 expected_step_count 等于简单3/中等4/困难5；steps编号1..N连续且N<=expected。颜色token蓝blue/绿green/黄yellow/红red/青teal；图片sun/coconut/boat/lighthouse/shell。每步selected/expected必须属于该难度前3/4/5个允许token，is_correct必须与两token相等一致。
- 顺序answered须N=expected，整题正确性=所有step正确；timeout须N<expected且整题false（允许0步）；interrupted只用于顺序，0<N<expected、只允许作为最后一题、整题false。这既保留timeout原有游戏评分行为，又不把主动退出的半题计入完成题/错误数/正确率。导出顺序题timeout/interrupted标“未完成”，实际step对错独立展示。
- v2非顺序 expected_step_count=null、selection_steps=[]；不允许interrupted。单次选择行为原样。拼图只完成题，click_count为非负整数、swap_count原样，click_count>=2*swap_count；每次可操作拼图块的有效点击计1，重复点同块取消也计数，预览/暂停/隐藏/结束按钮不计；未完成拼图按原行为不存。本次不扩展普通任意页面点击流水。
- 每题仍最多3600000毫秒整数；每步同范围；step毫秒总和<=整题毫秒；<=2000题，每题<=5步。游戏整场总时间约束与幂等/事务保持。旧版本不能混入v2新字段，v1仍不得interrupted；同一新场次不混采集版本。
- v2权威摘要completed_units/correct_units/error_count/accuracy_rate仅统计非interrupted题目（timeout继续按现行规则统计）。新增raw_detail.recorded_question_count=全部记录题数，仅v2写入。旧v1不加新派生字段以保留已持久化指纹。v2指纹包含全部步骤及点击数，重试元数据依旧剔除。
- v2采集题号按全部记录连续；每步耗时从允许本步作答到点击，首步从展示结束，后步从上一步点击；使用同一可暂停单调时钟，累计毫秒先round后相邻差分，保证步骤总和不超整题。展示/暂停/后台/阻塞语音/答后反馈不计。
- 顺序轮超时保留已选steps；主动结束或整场定时结束时保存当前已有steps为interrupted（若0步不新增）；已保存完整题或timeout不得重复追加。正常离页卸载也将已有进度同步放入既有待补传缓存，避免setState/网络回调操作卸载页面；仅后台隐藏保持暂停，不提前结束。复用原UUID重试内容，不添加新的患者提示。待补传支持多场排队，兼容原单对象缓存；保存新场次不得覆盖或丢弃旧场次，上传成功只移除对应场次，补传期间追加的数据保留。

## 存储、导出及兼容
- 新迁移0019（现叶节点0018）；不改0016/0017历史迁移，不补造旧选择步骤/点击数。父子写入同事务，失败全部回滚；解绑级联清理。
- 现5工作表增加第6表“顺序选择明细”，放在“游戏逐题”之后；每个已选步骤一行，含训练记录编号/训练日期/游戏编码/名称/题号/题目状态/选择序号/所选内容/正确内容/有效选择耗时（毫秒）/判定/实际难度。
- 游戏逐题仍每题一行：增加题目状态、已选择步数、应选择步数、拼图点击次数；保留每题总有效耗时和拼图实际交换次数，避免将总耗时重复到每一步。旧v1顺序题总耗时仍为已采集真实值，不补步骤；旧拼图click_count空，不用交换数推算。
- 没有可靠耗时的legacy仍不导出。仅合法v1/v2有效题出；v2步骤合法与父题有效时出新表，不导出任意原始载荷/URL。显示中文token标签，schema说明新增计时口径。格式版本training_detail_v2，审计/说明六表计数一致。
- 现每表200000/总500000行/10000场/60秒限制同样覆盖新表，不能截断；父子查询按批预取，避免N+1。整场摘要导出对v2按recorded_question_count与计入评分题数分别核对，不把合法interrupted视为数据丢失。

## 分工
1. backend代理：模型/迁移、v1/v2规范化与指纹/原子存储、定向测试；不碰export模块。
2. miniapp代理：questionCapture/游戏交互/卸载补传/类型/定向测试；不改backend。
3. 主控：现设计/计划修订、导出六表及对应测试/样本、必要Web提示、整体验证、独立审查和样本视觉。全量测试与构建在最终源码稳定时各跑一次。

## 2026-09-09 用户确认的导出列精简

所有工作表暂时移除起止时间可用性、游戏得分、逐题完整性、备注及其分段、窗口口径、心率/血压/血氧数据可用性、数据口径说明、全部动作质量详情分段列；字段说明同步去掉这些列的定义。仅调整Excel输出，不删除原始数据或改变有效耗时、正确性、运动统计和生理窗口计算。实施：统一输出列过滤，验证实际工作簿无遗漏并生成精简样本。
