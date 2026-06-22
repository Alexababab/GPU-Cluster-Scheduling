# GPU Cluster Scheduling

算法分析与设计（双语）课程设计项目。程序使用 C++17，从标准输入读取一个实例，并向标准输出写出恰好 `N` 行调度结果。

## 当前版本

V0 起点：顺序合法基线。所有任务串行执行，因此不会发生服务器并发资源冲突；它用于验证输入、输出、构建和后续优化接口，不代表最终竞赛策略。

## 构建与运行

```sh
sh build.sh
sh run.sh < tests/handcrafted/smoke.in
```

正式构建脚本直接调用 `g++`，减少评测环境依赖；`CMakeLists.txt` 供本地 IDE 和开发构建使用。

正式评测约束：

- Linux、C++17；
- 单实例单核 60 秒、内存 1 GB；
- `stdout` 只能包含调度记录；
- 每行格式：`task_id server_id start_time gpu_count finish_time`。

## 分支约定

- `main`：稳定与正式提交版本；
- `develop`：日常集成版本；
- `feature/<task>`：单项功能分支，从最新 `develop` 创建；
- 通过 Pull Request 合并，至少一名其他成员审查。

首轮建议分支：

- A：`feature/v0-core-greedy`
- B：`feature/v0-validator-evaluator`
- C：`feature/v0-batch-experiment`

## 目录

- `include/`、`src/`：主程序；
- `tests/handcrafted/`：手工小样例；
- `tools/`：验证、批处理与打包工具；
- `experiments/`：参数和实验结果；
- `research/strategy_cards/`：论文与工业方案策略卡；
- `docs/`：设计、会议和协作记录。
