# Scoring Calibration Checklist

Simplified counting checklists for manual calibration of the 30 sample questions in `data/sample_questions.json`, per [[22]] in `docs/decision_log.md` (manual calibration uses simplified hit-counts, not precomputed percentages).

For each question: count how many keyword clusters are hit (any synonym in a cluster counts as a hit for that cluster) and how many structure elements are present, then look up the percentage bands in `docs/scoring_rubric.md` yourself -- no need to compute percentages while reviewing.

逻辑连贯性 (logical coherence) and 具体性 (specificity) are generic across all question types (see `docs/scoring_rubric.md` sections 3.3 and 3.4) and are not counted here -- judge them directly against the five score bands (0-2/3-4/5-6/7-8/9-10).

---

## behavioral_01 (行为题)

**Question:** 请讲一次你在团队中发挥领导力、推动一个项目达成目标的经历。

### Keyword hit count (能力关键词库, 8 clusters)

Count a hit if the answer uses the canonical term OR any listed synonym.

- [ ] 领导力 / 带领团队 / 组织协调
- [ ] 目标拆解 / 任务分解 / 里程碑规划
- [ ] 授权 / 分工 / 委派任务
- [ ] 激励团队 / 调动积极性 / 打气鼓励
- [ ] 跨部门协作 / 跨团队沟通 / 协同配合
- [ ] 决策 / 拍板 / 做决定
- [ ] 复盘总结 / 事后回顾 / 经验沉淀
- [ ] 结果达成 / 按期交付 / 目标达成

**Hit count:** ___ / 8

### Structure element checklist (4 elements)

- [ ] 情境 (S)
- [ ] 任务 (T)
- [ ] 行动 (A)
- [ ] 结果 (R)

**Element count:** ___ / 4

### Reference points (for logical coherence / specificity judgment)

- 说明项目/团队背景及本人担任的角色
- 目标如何拆解、任务如何分配给团队成员
- 遇到的具体阻碍及如何协调资源/激励团队解决
- 可验证的结果（按期交付/量化指标）
- 简要复盘领导力方面的收获

---

## behavioral_02 (行为题)

**Question:** 说说一次你在高压力/紧迫deadline下完成工作的经历。

### Keyword hit count (能力关键词库, 8 clusters)

Count a hit if the answer uses the canonical term OR any listed synonym.

- [ ] 抗压 / 扛住压力 / 压力管理
- [ ] deadline / 截止日期 / 时间紧迫
- [ ] 优先级排序 / 分清主次 / 任务取舍
- [ ] 加班 / 额外投入 / 超时工作
- [ ] 情绪管理 / 保持冷静 / 不慌乱
- [ ] 资源协调 / 申请支持 / 寻求帮助
- [ ] 按时交付 / 如期完成 / 按期上线
- [ ] 复盘改进 / 事后总结 / 流程优化

**Hit count:** ___ / 8

### Structure element checklist (4 elements)

- [ ] 情境 (S)
- [ ] 任务 (T)
- [ ] 行动 (A)
- [ ] 结果 (R)

**Element count:** ___ / 4

### Reference points (for logical coherence / specificity judgment)

- 说明任务背景及紧迫的deadline
- 具体的时间/资源压力描述
- 如何排优先级、寻求支持、管理情绪
- 是否按时交付及交付质量
- 复盘：这次经历带来的抗压方法论

---

## behavioral_03 (行为题)

**Question:** 描述一次你和同事/上级意见不一致的经历，你是如何处理的。

### Keyword hit count (能力关键词库, 8 clusters)

Count a hit if the answer uses the canonical term OR any listed synonym.

- [ ] 冲突解决 / 化解分歧 / 处理矛盾
- [ ] 有效沟通 / 坦诚沟通 / 主动沟通
- [ ] 换位思考 / 同理心 / 理解对方立场
- [ ] 数据支撑 / 用事实说话 / 客观依据
- [ ] 折中方案 / 妥协 / 达成共识
- [ ] 保持专业 / 尊重对方 / 不情绪化
- [ ] 向上管理 / 说服上级 / 争取认同
- [ ] 关系维护 / 后续合作 / 结果验证

**Hit count:** ___ / 8

### Structure element checklist (4 elements)

- [ ] 情境 (S)
- [ ] 任务 (T)
- [ ] 行动 (A)
- [ ] 结果 (R)

**Element count:** ___ / 4

### Reference points (for logical coherence / specificity judgment)

- 说明分歧的具体内容和双方立场
- 采取的沟通方式（数据/换位思考等）
- 是否达成共识及最终方案
- 对后续合作关系的影响
- 复盘：从中学到的沟通/协作方法

---

## behavioral_04 (行为题)

**Question:** 讲一次你犯错或项目失败的经历，你是怎么应对和从中学习的。

### Keyword hit count (能力关键词库, 8 clusters)

Count a hit if the answer uses the canonical term OR any listed synonym.

- [ ] 承担责任 / 主动担责 / 不推诿
- [ ] 复盘反思 / 事后总结 / 归因分析
- [ ] 快速补救 / 止损 / 应急处理
- [ ] 透明沟通 / 主动汇报 / 如实告知
- [ ] 学习成长 / 吸取教训 / 能力提升
- [ ] 流程改进 / 建立机制 / 预防再犯
- [ ] 坦诚 / 不掩饰 / 诚实面对
- [ ] 后续验证 / 跟踪效果 / 持续改进

**Hit count:** ___ / 8

### Structure element checklist (4 elements)

- [ ] 情境 (S)
- [ ] 任务 (T)
- [ ] 行动 (A)
- [ ] 结果 (R)

**Element count:** ___ / 4

### Reference points (for logical coherence / specificity judgment)

- 说明错误/失败的具体情况
- 是否第一时间承担责任、如何补救
- 事后复盘归因及改进机制
- 是否有后续验证效果
- 从中学到的教训

---

## behavioral_05 (行为题)

**Question:** 说说一次你主动发现问题并推动解决的经历（无人要求你做）。

### Keyword hit count (能力关键词库, 8 clusters)

Count a hit if the answer uses the canonical term OR any listed synonym.

- [ ] 主动性 / 自驱力 / 不等指派
- [ ] 发现问题 / 识别风险 / 洞察隐患
- [ ] 推动落地 / 跟进执行 / 闭环解决
- [ ] 协调资源 / 说服他人 / 争取支持
- [ ] 超出职责 / 分外之事 / 额外付出
- [ ] 量化影响 / 数据佐证 / 证据支撑
- [ ] 主人翁意识 / 当自己是owner / 责任感
- [ ] 效果验证 / 成果衡量 / 后续跟踪

**Hit count:** ___ / 8

### Structure element checklist (4 elements)

- [ ] 情境 (S)
- [ ] 任务 (T)
- [ ] 行动 (A)
- [ ] 结果 (R)

**Element count:** ___ / 4

### Reference points (for logical coherence / specificity judgment)

- 说明是谁都没要求你做的问题
- 你如何发现问题、评估影响
- 如何说服他人/协调资源推动解决
- 最终结果及量化影响
- 复盘：主动性带来的价值

---

## behavioral_06 (行为题)

**Question:** 讲一次你需要同时处理多个优先级冲突任务的经历，你是如何排序和取舍的。

### Keyword hit count (能力关键词库, 8 clusters)

Count a hit if the answer uses the canonical term OR any listed synonym.

- [ ] 优先级排序 / 分清轻重缓急 / 任务排序
- [ ] 时间管理 / 日程安排 / 精力分配
- [ ] 预期管理 / 利益相关方沟通 / 协调多方
- [ ] 权衡取舍 / trade-off / 有舍有得
- [ ] 紧急重要矩阵 / 四象限 / 轻重缓急模型
- [ ] 协商延期 / 延期沟通 / 调整排期
- [ ] 结果交付 / 任务完成度 / 产出质量
- [ ] 复盘总结 / 经验沉淀 / 流程优化

**Hit count:** ___ / 8

### Structure element checklist (4 elements)

- [ ] 情境 (S)
- [ ] 任务 (T)
- [ ] 行动 (A)
- [ ] 结果 (R)

**Element count:** ___ / 4

### Reference points (for logical coherence / specificity judgment)

- 说明同时面临的多个任务及冲突点
- 排序依据（紧急重要/影响范围等）
- 如何与相关方沟通预期
- 最终完成情况
- 复盘：优先级方法论沉淀

---

## behavioral_07 (行为题)

**Question:** 说说一次你收到负面反馈或批评的经历，你是如何应对的。

### Keyword hit count (能力关键词库, 8 clusters)

Count a hit if the answer uses the canonical term OR any listed synonym.

- [ ] 接受反馈 / 虚心接受 / 不抵触
- [ ] 自我反思 / 内省 / 客观看待自己
- [ ] 情绪管理 / 不辩解 / 保持开放
- [ ] 主动澄清 / 理解反馈意图 / 确认具体点
- [ ] 行动改进 / 制定改进计划 / 付诸行动
- [ ] 跟进验证 / 后续检查 / 效果确认
- [ ] 建设性态度 / 感谢反馈 / 正向回应
- [ ] 成长心态 / growth mindset / 持续进步

**Hit count:** ___ / 8

### Structure element checklist (4 elements)

- [ ] 情境 (S)
- [ ] 任务 (T)
- [ ] 行动 (A)
- [ ] 结果 (R)

**Element count:** ___ / 4

### Reference points (for logical coherence / specificity judgment)

- 说明收到的具体反馈内容
- 当下的情绪反应及应对方式
- 如何澄清、制定改进计划
- 后续是否有改进验证
- 复盘：对反馈心态的转变

---

## behavioral_08 (行为题)

**Question:** 讲一次你在信息不完整/高度不确定的情况下做出决策的经历。

### Keyword hit count (能力关键词库, 8 clusters)

Count a hit if the answer uses the canonical term OR any listed synonym.

- [ ] 信息不完整 / 模糊性 / 不确定性
- [ ] 快速决策 / 果断行动 / 不过度分析
- [ ] 假设验证 / 小范围试错 / MVP验证
- [ ] 风险评估 / 识别风险点 / 权衡利弊
- [ ] 补充信息 / 数据收集 / 调研求证
- [ ] 灵活调整 / 根据反馈迭代 / 动态修正
- [ ] 承担后果 / 为决策负责 / 不推卸
- [ ] 结果复盘 / 验证决策效果 / 经验总结

**Hit count:** ___ / 8

### Structure element checklist (4 elements)

- [ ] 情境 (S)
- [ ] 任务 (T)
- [ ] 行动 (A)
- [ ] 结果 (R)

**Element count:** ___ / 4

### Reference points (for logical coherence / specificity judgment)

- 说明信息不完整的具体情境
- 如何评估风险、快速验证假设
- 决策依据是什么
- 结果如何、是否需要调整
- 复盘：模糊环境下的决策方法论

---

## behavioral_09 (行为题)

**Question:** 说说一次你说服他人（同事/客户/上级）接受你的观点或方案的经历。

### Keyword hit count (能力关键词库, 8 clusters)

Count a hit if the answer uses the canonical term OR any listed synonym.

- [ ] 说服力 / 影响力 / 争取认同
- [ ] 逻辑论证 / 结构化表达 / 有理有据
- [ ] 数据支撑 / 用事实说话 / 量化证明
- [ ] 理解诉求 / 换位思考 / 洞察利益点
- [ ] 方案对比 / 备选方案 / 权衡展示
- [ ] 耐心沟通 / 多轮沟通 / 持续跟进
- [ ] 达成一致 / 获得认可 / 最终采纳
- [ ] 结果验证 / 效果反馈 / 后续跟踪

**Hit count:** ___ / 8

### Structure element checklist (4 elements)

- [ ] 情境 (S)
- [ ] 任务 (T)
- [ ] 行动 (A)
- [ ] 结果 (R)

**Element count:** ___ / 4

### Reference points (for logical coherence / specificity judgment)

- 说明想要说服的对象及分歧点
- 采用的论证方式（数据/方案对比等）
- 沟通过程中的阻力及应对
- 是否最终达成一致
- 复盘：说服过程中的关键经验

---

## behavioral_10 (行为题)

**Question:** 讲一次你跨团队/跨部门协作完成一个项目的经历。

### Keyword hit count (能力关键词库, 8 clusters)

Count a hit if the answer uses the canonical term OR any listed synonym.

- [ ] 跨团队协作 / 跨部门配合 / 协同工作
- [ ] 目标对齐 / 利益对齐 / 消除分歧
- [ ] 沟通机制 / 定期同步 / 信息透明
- [ ] 角色分工 / 职责边界 / 明确接口
- [ ] 冲突处理 / 协调资源 / 化解摩擦
- [ ] 项目管理 / 进度跟踪 / 风险控制
- [ ] 共同目标 / 对齐KPI / 一致目标
- [ ] 最终交付 / 项目成功 / 协作成果

**Hit count:** ___ / 8

### Structure element checklist (4 elements)

- [ ] 情境 (S)
- [ ] 任务 (T)
- [ ] 行动 (A)
- [ ] 结果 (R)

**Element count:** ___ / 4

### Reference points (for logical coherence / specificity judgment)

- 说明涉及的团队及各自诉求
- 如何对齐目标、建立协作机制
- 遇到的冲突及协调方式
- 最终交付结果
- 复盘：跨团队协作的方法论

---

## technical_01 (技术题)

**Question:** 请设计一个短链接生成服务，说明你的整体方案。

### Keyword hit count (技术术语库, 9 clusters)

Count a hit if the answer uses the canonical term OR any listed synonym.

- [ ] 哈希算法 / hash函数 / 摘要算法
- [ ] Base62编码 / 进制转换编码 / 短码生成
- [ ] 唯一性冲突 / 碰撞处理 / 去重机制
- [ ] 存储方案 / 数据库设计 / 索引设计
- [ ] 缓存 / cache / Redis缓存
- [ ] 并发量 / QPS / 吞吐量
- [ ] 水平扩展 / 分布式部署 / 负载均衡
- [ ] 过期策略 / TTL / 过期清理
- [ ] 限流 / 防刷 / rate limiting

**Hit count:** ___ / 9

### Structure element checklist (4 elements)

- [ ] 问题描述
- [ ] 技术方案
- [ ] 权衡讨论
- [ ] 结论

**Element count:** ___ / 4

### Reference points (for logical coherence / specificity judgment)

- 生成算法选型（自增ID+Base62 / hash+去重）及冲突处理
- 存储与索引设计（短码到长链接的映射）
- 高频读取的缓存策略
- 高并发下的扩展方案（分库分表/发号器）
- 过期策略与防刷限流

---

## technical_02 (技术题)

**Question:** 谈谈你对缓存穿透、缓存击穿、缓存雪崩的理解及解决方案。

### Keyword hit count (技术术语库, 9 clusters)

Count a hit if the answer uses the canonical term OR any listed synonym.

- [ ] 缓存穿透 / cache penetration / 无效key攻击
- [ ] 缓存击穿 / cache breakdown / 热点key失效
- [ ] 缓存雪崩 / cache avalanche / 大规模同时失效
- [ ] 布隆过滤器 / bloom filter / 过滤无效请求
- [ ] 空值缓存 / 缓存空对象 / null caching
- [ ] 互斥锁 / mutex lock / 分布式锁
- [ ] 过期时间打散 / 随机TTL / 错峰过期
- [ ] 多级缓存 / 本地缓存+分布式缓存 / 二级缓存
- [ ] 降级熔断 / 服务降级 / 熔断机制

**Hit count:** ___ / 9

### Structure element checklist (4 elements)

- [ ] 问题描述
- [ ] 技术方案
- [ ] 权衡讨论
- [ ] 结论

**Element count:** ___ / 4

### Reference points (for logical coherence / specificity judgment)

- 三种问题的定义区分
- 穿透的解决方案（布隆过滤器/空值缓存）
- 击穿的解决方案（互斥锁/逻辑过期）
- 雪崩的解决方案（过期时间打散/多级缓存/降级熔断）
- 结合具体场景说明为什么选择该方案

---

## technical_03 (技术题)

**Question:** 请解释CAP定理，并说明在设计分布式系统时如何取舍。

### Keyword hit count (技术术语库, 9 clusters)

Count a hit if the answer uses the canonical term OR any listed synonym.

- [ ] CAP定理 / CAP theorem / 一致性可用性分区容错
- [ ] 一致性 / consistency / 数据一致
- [ ] 可用性 / availability / 服务可用
- [ ] 分区容错 / partition tolerance / 网络分区
- [ ] 最终一致性 / eventual consistency / 异步同步
- [ ] 强一致性 / strong consistency / 线性一致性
- [ ] CP/AP权衡 / CP系统 / AP系统
- [ ] 幂等性 / idempotency / 重复请求处理
- [ ] BASE理论 / 软状态 / 基本可用

**Hit count:** ___ / 9

### Structure element checklist (4 elements)

- [ ] 问题描述
- [ ] 技术方案
- [ ] 权衡讨论
- [ ] 结论

**Element count:** ___ / 4

### Reference points (for logical coherence / specificity judgment)

- CAP三要素的准确定义
- 分区容错在分布式系统中不可放弃的原因
- CP vs AP的权衡实例
- 最终一致性与强一致性的区别
- 结合具体系统（如注册中心/数据库）说明取舍

---

## technical_04 (技术题)

**Question:** 讲讲数据库慢查询如何排查和优化，重点谈谈索引设计。

### Keyword hit count (技术术语库, 9 clusters)

Count a hit if the answer uses the canonical term OR any listed synonym.

- [ ] 索引 / index / B+树索引
- [ ] 执行计划 / explain / 查询计划分析
- [ ] 联合索引 / 复合索引 / 组合索引
- [ ] 最左前缀 / leftmost prefix / 索引匹配原则
- [ ] 覆盖索引 / covering index / 索引覆盖
- [ ] 全表扫描 / table scan / 全表遍历
- [ ] 慢查询日志 / slow query log / 慢日志分析
- [ ] 索引选择性 / cardinality / 区分度
- [ ] 回表 / index lookup / 二次查询

**Hit count:** ___ / 9

### Structure element checklist (4 elements)

- [ ] 问题描述
- [ ] 技术方案
- [ ] 权衡讨论
- [ ] 结论

**Element count:** ___ / 4

### Reference points (for logical coherence / specificity judgment)

- 排查思路（慢查询日志+执行计划）
- 索引类型及适用场景（联合索引/覆盖索引）
- 最左前缀原则
- 索引选择性与区分度
- 回表问题及优化方式

---

## technical_05 (技术题)

**Question:** 说说消息队列的作用及如何设计一个削峰填谷的方案。

### Keyword hit count (技术术语库, 9 clusters)

Count a hit if the answer uses the canonical term OR any listed synonym.

- [ ] 消息队列 / MQ / message queue
- [ ] 削峰填谷 / 流量削峰 / peak shaving
- [ ] 异步解耦 / asynchronous decoupling / 服务解耦
- [ ] 生产者消费者 / producer consumer / 发布订阅
- [ ] 消息堆积 / backlog / 积压处理
- [ ] 消息可靠性 / 消息丢失 / 持久化
- [ ] 消息幂等 / 去重消费 / exactly-once
- [ ] 死信队列 / dead letter queue / 异常消息处理
- [ ] 限流 / 流量控制 / rate limiting

**Hit count:** ___ / 9

### Structure element checklist (4 elements)

- [ ] 问题描述
- [ ] 技术方案
- [ ] 权衡讨论
- [ ] 结论

**Element count:** ___ / 4

### Reference points (for logical coherence / specificity judgment)

- 消息队列的解耦/异步/削峰作用
- 具体的削峰方案设计（生产者限流+队列缓冲+消费者匀速消费）
- 消息堆积的应对
- 消息可靠性保证（持久化/确认机制）
- 消息幂等/去重处理

---

## technical_06 (技术题)

**Question:** 请说明什么是灰度发布，以及你会如何设计灰度发布方案。

### Keyword hit count (技术术语库, 9 clusters)

Count a hit if the answer uses the canonical term OR any listed synonym.

- [ ] 灰度发布 / canary release / 金丝雀发布
- [ ] 蓝绿部署 / blue-green deployment / 蓝绿切换
- [ ] 流量分层 / 流量切分 / 分流策略
- [ ] 回滚机制 / rollback / 快速回退
- [ ] 监控告警 / monitoring alerting / 指标监控
- [ ] 特征开关 / feature flag / 功能开关
- [ ] 用户分群 / 分桶 / 灰度人群圈定
- [ ] 版本兼容 / 向后兼容 / 接口兼容性
- [ ] 健康检查 / 自动化验证 / health check

**Hit count:** ___ / 9

### Structure element checklist (4 elements)

- [ ] 问题描述
- [ ] 技术方案
- [ ] 权衡讨论
- [ ] 结论

**Element count:** ___ / 4

### Reference points (for logical coherence / specificity judgment)

- 灰度发布的定义及与蓝绿部署的区别
- 流量分层/分桶策略
- 监控指标及自动/手动回滚机制
- 特征开关的使用
- 用户分群圈定方式

---

## technical_07 (技术题)

**Question:** 谈谈你会如何设计一个API限流方案。

### Keyword hit count (技术术语库, 9 clusters)

Count a hit if the answer uses the canonical term OR any listed synonym.

- [ ] 限流 / rate limiting / 流量控制
- [ ] 令牌桶 / token bucket / 令牌桶算法
- [ ] 漏桶算法 / leaky bucket / 漏桶限流
- [ ] 滑动窗口 / sliding window / 计数窗口
- [ ] 分布式限流 / 集群限流 / 全局限流
- [ ] 熔断降级 / circuit breaker / 服务熔断
- [ ] 黑白名单 / IP限制 / 访问控制
- [ ] QPS阈值 / 并发阈值 / 流量阈值
- [ ] 限流反馈 / 429响应 / 限流提示

**Hit count:** ___ / 9

### Structure element checklist (4 elements)

- [ ] 问题描述
- [ ] 技术方案
- [ ] 权衡讨论
- [ ] 结论

**Element count:** ___ / 4

### Reference points (for logical coherence / specificity judgment)

- 限流算法对比（令牌桶/漏桶/滑动窗口）
- 单机限流 vs 分布式限流
- 限流粒度（用户/IP/接口）
- 超限后的处理方式（排队/拒绝/降级）
- 与熔断降级的配合

---

## technical_08 (技术题)

**Question:** 请设计一个高并发秒杀系统，说明关键难点和解决方案。

### Keyword hit count (技术术语库, 9 clusters)

Count a hit if the answer uses the canonical term OR any listed synonym.

- [ ] 秒杀系统 / seckill system / 高并发抢购
- [ ] 库存超卖 / 超卖问题 / 库存扣减
- [ ] 分布式锁 / distributed lock / 锁竞争
- [ ] 限流削峰 / 流量削峰 / 请求过滤
- [ ] 缓存预热 / cache warm up / 预加载库存
- [ ] 异步下单 / 消息队列异步 / 削峰异步化
- [ ] 页面静态化 / 静态化 / CDN加速
- [ ] 防刷风控 / 验证码风控 / 反作弊
- [ ] 原子操作 / 乐观锁 / CAS操作

**Hit count:** ___ / 9

### Structure element checklist (4 elements)

- [ ] 问题描述
- [ ] 技术方案
- [ ] 权衡讨论
- [ ] 结论

**Element count:** ___ / 4

### Reference points (for logical coherence / specificity judgment)

- 核心难点（超卖/高并发/瞬时流量）
- 库存扣减方案（数据库乐观锁/Redis原子操作）
- 限流+异步削峰设计
- 缓存预热与页面静态化
- 防刷风控机制

---

## technical_09 (技术题)

**Question:** 说说什么是分布式锁，以及常见的实现方式和陷阱。

### Keyword hit count (技术术语库, 9 clusters)

Count a hit if the answer uses the canonical term OR any listed synonym.

- [ ] 分布式锁 / distributed lock / 跨进程加锁
- [ ] Redis锁 / Redisson / SET NX实现
- [ ] ZooKeeper锁 / 临时节点 / Zab协议
- [ ] 锁续期 / 看门狗 / 续期机制
- [ ] 死锁 / deadlock / 锁未释放
- [ ] 脑裂 / split brain / 网络分区一致性问题
- [ ] 可重入锁 / reentrant lock / 重入机制
- [ ] 锁超时 / 过期时间 / TTL设置
- [ ] 原子性保证 / CAS / 原子操作

**Hit count:** ___ / 9

### Structure element checklist (4 elements)

- [ ] 问题描述
- [ ] 技术方案
- [ ] 权衡讨论
- [ ] 结论

**Element count:** ___ / 4

### Reference points (for logical coherence / specificity judgment)

- 常见实现方式（Redis/ZooKeeper）对比
- 锁超时与续期机制（看门狗）
- 可重入性设计
- 脑裂/网络分区场景下的风险
- 释放锁的原子性保证

---

## technical_10 (技术题)

**Question:** 谈谈微服务架构下如何做可观测性建设（日志/监控/链路追踪）。

### Keyword hit count (技术术语库, 9 clusters)

Count a hit if the answer uses the canonical term OR any listed synonym.

- [ ] 可观测性 / observability / 监控体系
- [ ] 日志采集 / log collection / 集中式日志
- [ ] 链路追踪 / distributed tracing / 调用链追踪
- [ ] 指标监控 / metrics / 监控指标
- [ ] 告警机制 / alerting / 告警规则
- [ ] APM / 应用性能监控 / 性能剖析
- [ ] Trace ID / 请求追踪ID / 上下文透传
- [ ] 监控大盘 / Prometheus/Grafana / 可视化面板
- [ ] SLA/SLO / 服务水平目标 / 可用性指标

**Hit count:** ___ / 9

### Structure element checklist (4 elements)

- [ ] 问题描述
- [ ] 技术方案
- [ ] 权衡讨论
- [ ] 结论

**Element count:** ___ / 4

### Reference points (for logical coherence / specificity judgment)

- 日志/监控/链路追踪三大支柱定义
- 链路追踪的实现方式（Trace ID透传）
- 监控指标体系设计（黄金指标/SLA）
- 告警规则设计
- 常用工具栈举例

---

## case_analysis_01 (案例分析题)

**Question:** 某电商App的日活用户（DAU）近两周下滑了15%，请分析可能原因并给出解决方案。

### Keyword hit count (分析框架术语库, 9 clusters)

Count a hit if the answer uses the canonical term OR any listed synonym.

- [ ] MECE / 相互独立完全穷尽 / 结构化拆解
- [ ] 漏斗分析 / 转化漏斗 / funnel analysis
- [ ] 归因分析 / 根因分析 / root cause
- [ ] 同比环比 / yoy mom / 基准对比
- [ ] 用户分群 / 分层分析 / cohort分析
- [ ] A/B测试 / AB test / 实验验证
- [ ] 北极星指标 / North Star Metric / 核心指标
- [ ] 优先级排序 / ICE/RICE模型 / impact effort
- [ ] 短期长期区分 / 止血vs优化 / 治标治本

**Hit count:** ___ / 9

### Structure element checklist (5 elements)

- [ ] 问题界定 (Define)
- [ ] 框架拆解 (Structure)
- [ ] 验证排查 (Diagnose)
- [ ] 方案与优先级 (Prioritize)
- [ ] 结论与验证机制 (Conclude)

**Element count:** ___ / 5

### Reference points (for logical coherence / specificity judgment)

- 界定：确认下滑口径（同比/环比、全量/细分人群）及是否持续性趋势
- 拆解：按获客-激活-留存-转化漏斗+渠道/新老用户交叉MECE拆解
- 验证：版本更新前后对比、分渠道cohort对比、排查外部竞品因素
- 方案：区分技术故障类止血与渠道/内容类长期优化，按影响排优先级
- 结论：设定观察周期持续监控DAU及分渠道留存指标

---

## case_analysis_02 (案例分析题)

**Question:** 某内容平台的新用户次日留存率从40%下降到30%，请分析原因并提出方案。

### Keyword hit count (分析框架术语库, 9 clusters)

Count a hit if the answer uses the canonical term OR any listed synonym.

- [ ] 留存分析 / retention analysis / 留存曲线
- [ ] 漏斗分析 / 转化路径 / funnel
- [ ] MECE / 结构化拆解 / 穷尽分类
- [ ] cohort对比 / 新老用户对比 / 分群对比
- [ ] 渠道质量 / 获客渠道 / 渠道归因
- [ ] 产品体验 / onboarding / 新手引导
- [ ] A/B测试 / 实验对照 / 灰度验证
- [ ] 北极星指标 / 核心指标 / 关键指标
- [ ] 优先级排序 / 短期止血长期优化 / impact effort

**Hit count:** ___ / 9

### Structure element checklist (5 elements)

- [ ] 问题界定 (Define)
- [ ] 框架拆解 (Structure)
- [ ] 验证排查 (Diagnose)
- [ ] 方案与优先级 (Prioritize)
- [ ] 结论与验证机制 (Conclude)

**Element count:** ___ / 5

### Reference points (for logical coherence / specificity judgment)

- 界定：确认次留统计口径及下滑是否分渠道分人群一致
- 拆解：按onboarding-核心行为-召回路径拆漏斗，按渠道/新老用户分群
- 验证：对比版本迭代前后曲线、渠道质量交叉分析、用户访谈
- 方案：短期修复明显bug/体验问题，长期优化新手引导
- 结论：持续监控次留曲线，设定观察周期

---

## case_analysis_03 (案例分析题)

**Question:** 某在线教育产品的付费转化率连续一个月下降，请分析原因并给出解决思路。

### Keyword hit count (分析框架术语库, 9 clusters)

Count a hit if the answer uses the canonical term OR any listed synonym.

- [ ] 转化漏斗 / 付费转化路径 / funnel analysis
- [ ] MECE拆解 / 结构化分析 / 穷尽拆解
- [ ] 定价策略 / pricing / 价格敏感度
- [ ] 竞品分析 / 竞争环境 / 外部因素
- [ ] 用户分群 / 渠道/新老用户拆分 / cohort
- [ ] A/B测试 / 实验验证 / 灰度测试
- [ ] 归因分析 / 根因定位 / root cause
- [ ] 北极星指标 / 核心业务指标 / 付费GMV
- [ ] 优先级排序 / 止血vs优化 / 短期长期区分

**Hit count:** ___ / 9

### Structure element checklist (5 elements)

- [ ] 问题界定 (Define)
- [ ] 框架拆解 (Structure)
- [ ] 验证排查 (Diagnose)
- [ ] 方案与优先级 (Prioritize)
- [ ] 结论与验证机制 (Conclude)

**Element count:** ___ / 5

### Reference points (for logical coherence / specificity judgment)

- 界定：确认转化率口径（哪一步到哪一步）、下滑是否所有课程/渠道一致
- 拆解：按转化漏斗（浏览-试听-加购-支付）拆解，按渠道/课程品类/价格带分群
- 验证：对比竞品定价、检查支付链路是否有技术故障、用户调研购买顾虑
- 方案：短期修复技术问题/优化支付流程，长期调整定价或课程内容策略
- 结论：跟踪转化率恢复情况，设定复盘周期

---

## case_analysis_04 (案例分析题)

**Question:** 公司新上线的一个功能，上线一个月后核心指标远低于预期，请分析原因。

### Keyword hit count (分析框架术语库, 9 clusters)

Count a hit if the answer uses the canonical term OR any listed synonym.

- [ ] MECE / 结构化拆解 / 相互独立完全穷尽
- [ ] 功能渗透率 / feature adoption / 使用率
- [ ] 用户分群 / 新老用户对比 / 分层分析
- [ ] 埋点数据 / 数据验证 / tracking核查
- [ ] 用户访谈 / 定性调研 / user interview
- [ ] A/B测试 / 实验对照 / 灰度验证
- [ ] 归因分析 / 根因分析 / root cause
- [ ] 优先级排序 / ICE/RICE模型 / impact effort
- [ ] 止损方案 / 短期止血长期优化 / 迭代优化

**Hit count:** ___ / 9

### Structure element checklist (5 elements)

- [ ] 问题界定 (Define)
- [ ] 框架拆解 (Structure)
- [ ] 验证排查 (Diagnose)
- [ ] 方案与优先级 (Prioritize)
- [ ] 结论与验证机制 (Conclude)

**Element count:** ___ / 5

### Reference points (for logical coherence / specificity judgment)

- 界定：确认预期指标口径、功能渗透率现状、上线时间与观察窗口
- 拆解：按功能渗透率-使用深度-留存影响拆解，按用户分群看谁在用谁没用
- 验证：核查埋点数据是否准确、用户访谈了解为何不用、A/B测试对照组差异
- 方案：短期修复明显的可用性问题，长期迭代功能设计或调整目标用户定位
- 结论：设定新的观察周期重新评估指标

---

## case_analysis_05 (案例分析题)

**Question:** 某电商平台GMV（成交总额）同比下滑，请分析可能原因并给出应对方案。

### Keyword hit count (分析框架术语库, 9 clusters)

Count a hit if the answer uses the canonical term OR any listed synonym.

- [ ] GMV拆解 / 客单价×订单数 / 公式化拆解
- [ ] MECE / 结构化拆解 / 穷尽分类
- [ ] 漏斗分析 / 转化路径分析 / funnel
- [ ] 渠道归因 / 获客渠道分析 / 流量来源
- [ ] 季节性因素 / 外部环境 / 大盘趋势
- [ ] 竞品分析 / 市场竞争 / 外部因素排查
- [ ] A/B测试 / 实验验证 / 灰度测试
- [ ] 北极星指标 / 核心业务指标 / 关键指标
- [ ] 优先级排序 / 短期长期区分 / impact effort

**Hit count:** ___ / 9

### Structure element checklist (5 elements)

- [ ] 问题界定 (Define)
- [ ] 框架拆解 (Structure)
- [ ] 验证排查 (Diagnose)
- [ ] 方案与优先级 (Prioritize)
- [ ] 结论与验证机制 (Conclude)

**Element count:** ___ / 5

### Reference points (for logical coherence / specificity judgment)

- 界定：GMV=客单价×订单数×转化率，先确认是哪个因子下滑
- 拆解：按品类/渠道/地域/新老用户MECE拆解，排查外部季节性和竞品因素
- 验证：交叉分析各细分维度数据，核实是否有促销活动缺失或竞品大促分流
- 方案：短期针对性促销拉回，长期优化商品结构或渠道投放
- 结论：跟踪GMV和各拆解因子的恢复情况

---

## case_analysis_06 (案例分析题)

**Question:** 客服满意度评分近期明显下降，请分析原因并提出改进方案。

### Keyword hit count (分析框架术语库, 9 clusters)

Count a hit if the answer uses the canonical term OR any listed synonym.

- [ ] MECE拆解 / 结构化分析 / 穷尽分类
- [ ] 用户分群 / 按问题类型分层 / 渠道分层
- [ ] 根因分析 / 归因分析 / root cause
- [ ] 数据交叉分析 / 多维交叉 / cross analysis
- [ ] 用户访谈 / 定性调研 / 满意度回访
- [ ] A/B测试 / 流程实验 / 灰度验证
- [ ] SLA / 响应时长 / 服务水平
- [ ] 优先级排序 / ICE/RICE模型 / impact effort
- [ ] 短期长期区分 / 止血vs优化 / 治标治本

**Hit count:** ___ / 9

### Structure element checklist (5 elements)

- [ ] 问题界定 (Define)
- [ ] 框架拆解 (Structure)
- [ ] 验证排查 (Diagnose)
- [ ] 方案与优先级 (Prioritize)
- [ ] 结论与验证机制 (Conclude)

**Element count:** ___ / 5

### Reference points (for logical coherence / specificity judgment)

- 界定：确认满意度下降是全渠道全品类还是集中在某问题类型/渠道
- 拆解：按问题类型、客服渠道、响应时长几个维度MECE拆解
- 验证：交叉分析低分评价的具体反馈内容，回访典型低分用户
- 方案：短期针对高频差评问题类型专项优化，长期改进培训/流程/工具
- 结论：跟踪满意度分和SLA指标变化

---

## case_analysis_07 (案例分析题)

**Question:** 某App的广告投放ROI（投入产出比）持续走低，请分析原因并给出优化建议。

### Keyword hit count (分析框架术语库, 9 clusters)

Count a hit if the answer uses the canonical term OR any listed synonym.

- [ ] ROI拆解 / 公式化拆解 / 投入产出分解
- [ ] MECE / 结构化拆解 / 穷尽分类
- [ ] 渠道归因 / 投放渠道分析 / channel attribution
- [ ] 用户质量 / LTV / 用户生命周期价值
- [ ] 竞品分析 / 外部环境 / 市场竞争
- [ ] A/B测试 / 素材实验 / 灰度测试
- [ ] 归因分析 / 根因定位 / root cause
- [ ] 北极星指标 / 核心指标 / 关键业务指标
- [ ] 优先级排序 / 短期长期区分 / impact effort

**Hit count:** ___ / 9

### Structure element checklist (5 elements)

- [ ] 问题界定 (Define)
- [ ] 框架拆解 (Structure)
- [ ] 验证排查 (Diagnose)
- [ ] 方案与优先级 (Prioritize)
- [ ] 结论与验证机制 (Conclude)

**Element count:** ___ / 5

### Reference points (for logical coherence / specificity judgment)

- 界定：ROI=收入/投放成本，确认是收入端还是成本端出问题
- 拆解：按投放渠道/素材/人群包MECE拆解，排查竞价环境变化等外部因素
- 验证：分渠道分素材做归因分析，评估用户LTV是否同步下降
- 方案：短期暂停低效渠道/素材，长期优化投放策略和用户质量筛选
- 结论：跟踪分渠道ROI恢复情况

---

## case_analysis_08 (案例分析题)

**Question:** 某App的崩溃率（Crash Rate）近期明显上升，请分析原因并给出解决方案。

### Keyword hit count (分析框架术语库, 9 clusters)

Count a hit if the answer uses the canonical term OR any listed synonym.

- [ ] MECE拆解 / 结构化分析 / 穷尽分类
- [ ] 版本对比 / 版本归因 / release对比
- [ ] 设备/机型分布 / 环境分层 / segment分析
- [ ] 日志分析 / crash log / 堆栈分析
- [ ] 灰度发布 / canary release / 分批验证
- [ ] A/B测试 / 实验对照 / 灰度回滚
- [ ] 根因分析 / 归因分析 / root cause
- [ ] 优先级排序 / ICE/RICE模型 / impact effort
- [ ] 止血方案 / hotfix vs 长期修复 / 短期长期区分

**Hit count:** ___ / 9

### Structure element checklist (5 elements)

- [ ] 问题界定 (Define)
- [ ] 框架拆解 (Structure)
- [ ] 验证排查 (Diagnose)
- [ ] 方案与优先级 (Prioritize)
- [ ] 结论与验证机制 (Conclude)

**Element count:** ___ / 5

### Reference points (for logical coherence / specificity judgment)

- 界定：确认崩溃率统计口径、上升时间点是否对应某次版本发布
- 拆解：按版本/机型/系统版本/地域MECE拆解崩溃分布
- 验证：分析崩溃日志堆栈定位具体代码问题，灰度对比新旧版本崩溃率
- 方案：短期紧急发布hotfix或灰度回滚，长期加强发布前测试覆盖
- 结论：跟踪崩溃率恢复至正常水平，复盘发布流程

---

## case_analysis_09 (案例分析题)

**Question:** 公司整体收入下滑，但用户数量仍在正常增长，请分析可能原因。

### Keyword hit count (分析框架术语库, 9 clusters)

Count a hit if the answer uses the canonical term OR any listed synonym.

- [ ] MECE拆解 / 结构化分析 / 穷尽分类
- [ ] 收入公式拆解 / 客单价×付费率×用户数 / 公式化拆解
- [ ] 用户分群 / 付费用户vs免费用户 / cohort分析
- [ ] 渠道归因 / 获客渠道质量 / 流量结构变化
- [ ] 竞品分析 / 市场竞争 / 外部环境
- [ ] A/B测试 / 实验验证 / 灰度测试
- [ ] 归因分析 / 根因分析 / root cause
- [ ] 北极星指标 / 核心业务指标 / 关键指标
- [ ] 优先级排序 / 短期长期区分 / impact effort

**Hit count:** ___ / 9

### Structure element checklist (5 elements)

- [ ] 问题界定 (Define)
- [ ] 框架拆解 (Structure)
- [ ] 验证排查 (Diagnose)
- [ ] 方案与优先级 (Prioritize)
- [ ] 结论与验证机制 (Conclude)

**Element count:** ___ / 5

### Reference points (for logical coherence / specificity judgment)

- 界定：收入=用户数×付费率×客单价，确认是付费率还是客单价下滑
- 拆解：按新老用户/渠道/付费档位MECE拆解，排查获客渠道结构变化
- 验证：交叉分析新增用户的付费转化质量，对比历史同期基准
- 方案：短期优化付费转化路径，长期调整获客渠道结构和定价策略
- 结论：跟踪付费率和客单价的恢复情况

---

## case_analysis_10 (案例分析题)

**Question:** 产品核心指标增长明显放缓，请分析可能的突破方向。

### Keyword hit count (分析框架术语库, 9 clusters)

Count a hit if the answer uses the canonical term OR any listed synonym.

- [ ] MECE拆解 / 结构化分析 / 穷尽分类
- [ ] 增长模型 / AARRR模型 / 海盗指标模型
- [ ] 用户分群 / 分层分析 / cohort分析
- [ ] 天花板分析 / 市场饱和度 / 渗透率分析
- [ ] 竞品分析 / 外部环境 / 市场对比
- [ ] A/B测试 / 实验验证 / 灰度测试
- [ ] 归因分析 / 根因定位 / root cause
- [ ] 北极星指标 / 核心业务指标 / 关键指标
- [ ] 优先级排序 / ICE/RICE模型 / impact effort

**Hit count:** ___ / 9

### Structure element checklist (5 elements)

- [ ] 问题界定 (Define)
- [ ] 框架拆解 (Structure)
- [ ] 验证排查 (Diagnose)
- [ ] 方案与优先级 (Prioritize)
- [ ] 结论与验证机制 (Conclude)

**Element count:** ___ / 5

### Reference points (for logical coherence / specificity judgment)

- 界定：确认放缓的具体指标和时间节点、是否已接近渗透天花板
- 拆解：用AARRR模型拆解各环节增长贡献，分市场/人群看是否结构性放缓
- 验证：对比竞品增长曲线判断是否行业性放缓，评估存量市场饱和度
- 方案：短期优化现有环节转化效率，长期探索新市场/新用户群/新场景
- 结论：设定新的增长目标和监控指标观察突破效果

---
