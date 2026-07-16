# 任务配置说明

MAA 支持的任务类型和参数说明。

## 使用方法

```bash
# 使用默认启动任务
python main.py startup

# 使用日常任务
python main.py daily

# 使用副本任务
python main.py fight

# 指定完整路径
python main.py -t tasks/full.json
```

## 任务类型列表

| 任务类型 | 说明 |
|---------|------|
| `StartUp` | 启动游戏 / 唤醒 |
| `CloseDown` | 关闭游戏 |
| `Fight` | 刷副本 / 作战 |
| `Recruit` | 公开招募 |
| `Infrast` | 基建换班 |
| `Mall` | 信用商店 |
| `Award` | 领取奖励 |
| `Roguelike` | 集成战略 |
| `Reclamation` | 保全派驻 |
| `Copilot` | 自定义战斗 (小助手) |
| `SSSCopilot` | 保全派驻小助手 |
| `ParadoxCopilot` | 悖论模拟 |
| `Depot` | 仓库识别 |
| `OperBox` | 干员 box 识别 |
| `Custom` | 自定义任务 |

## 各任务参数说明

### StartUp - 启动游戏

```json
{
    "name": "启动",
    "type": "StartUp",
    "params": {
        "client_type": "Official",
        "start_game_enabled": false
    }
}
```

| 参数 | 说明 |
|-----|------|
| `client_type` | 客户端类型: `Official`/`YoStarEN`/`YoStarJP`/`YoStarKR`/`txwy`/`Bilibili` |
| `start_game_enabled` | 是否自动启动游戏 |

### Fight - 刷副本

```json
{
    "name": "刷副本",
    "type": "Fight",
    "params": {
        "stage": "1-7",
        "medicine": 0,
        "expiring_medicine": 0,
        "stone": 0,
        "times": 100,
        "series": 0,
        "DrGrandet": false,
        "report_to_penguin": false,
        "penguin_id": "",
        "client_type": "Official"
    }
}
```

| 参数 | 说明 |
|-----|------|
| `stage` | 关卡名, 例如 `1-7`, `CE-6`, `SL-8` 等 |
| `medicine` | 理智药使用数量 |
| `expiring_medicine` | 过期理智药使用数量 |
| `stone` | 源石使用数量 |
| `times` | 最大通关次数 |
| `series` | 重复作战次数 (-1=不切换, 0=自动, 1~6=指定次数) |
| `DrGrandet` | 是否当葛朗台 (等 1 点理智才用石头) |
| `report_to_penguin` | 是否汇报到企鹅物流数据统计 |
| `penguin_id` | 企鹅物流 ID (可选) |
| `drops` | 指定掉落数量停止, 例如 `{"30012": 100}` |

### Infrast - 基建换班

```json
{
    "name": "基建",
    "type": "Infrast",
    "params": {
        "mode": 10000,
        "facility": ["Trade", "Dorm", "Control", "Reception", "Office", "Mfg", "Power"],
        "dorm_trust_enabled": true,
        "filename": "normal.json",
        "plan_index": 0
    }
}
```

| 参数 | 说明 |
|-----|------|
| `mode` | 工作模式 (10000=全部换班) |
| `facility` | 设施列表: `Trade`(贸易站), `Dorm`(宿舍), `Control`(控制中心), `Reception`(会客室), `Office`(办公室), `Mfg`(制造站), `Power`(发电站) |
| `dorm_trust_enabled` | 是否自动填充信赖 |
| `filename` | 使用的换班计划文件名 |
| `plan_index` | 计划索引 (0, 1, 2...) |

### Recruit - 公开招募

```json
{
    "name": "公开招募",
    "type": "Recruit",
    "params": {
        "select": [4],
        "confirm": [3, 4],
        "times": 4,
        "set_time": true,
        "report_to_penguin": false
    }
}
```

| 参数 | 说明 |
|-----|------|
| `select` | 选择的标签组合 (3=四星, 4=五星, 5=六星) |
| `confirm` | 确认招募的星级 (3=四星, 4=五星, 5=六星) |
| `times` | 招募次数 |
| `set_time` | 是否自动拉满9小时 |

### Mall - 信用商店

```json
{
    "name": "信用商店",
    "type": "Mall",
    "params": {
        "shopping": true,
        "credit_fight": false,
        "buy_first": ["招聘许可", "龙门币", "加急许可"],
        "blacklist": ["家具", "碳"]
    }
}
```

| 参数 | 说明 |
|-----|------|
| `shopping` | 是否购物 |
| `credit_fight` | 是否信用对战 |
| `buy_first` | 优先购买列表 |
| `blacklist` | 黑名单 (不买) |

### Roguelike - 集成战略

```json
{
    "name": "集成战略",
    "type": "Roguelike",
    "params": {
        "theme": "Sami",
        "mode": 0,
        "starts_count": 1,
        "investment_enabled": true,
        "investments_count": 0,
        "stop_when_investment_full": true,
        "squad": "指挥分队",
        "roles": "顺其自然",
        "core_char": "棘刺",
        "use_support": false,
        "use_nonfriend_support": false
    }
}
```

| 参数 | 说明 |
|-----|------|
| `theme` | 主题: `Phantom`(傀影与猩红孤钻)/`Mizuki`(水月与深蓝之树)/`Sami`(探索者的银凇止境) |
| `mode` | 模式: 0=刷投资/1=刷第N层/2=通关/3=分队 |
| `starts_count` | 开始探索次数 |
| `investment_enabled` | 是否投资 |
| `investments_count` | 投资次数限制 |
| `stop_when_investment_full` | 投资满了就停 |
| `squad` | 队伍名 |
| `roles` | 角色定位 |
| `core_char` | 核心干员名 |
| `use_support` | 是否用助战 |
| `use_nonfriend_support` | 是否用非好友助战 |

### Award - 领取奖励

```json
{
    "name": "领取奖励",
    "type": "Award",
    "params": {}
}
```

### Visit - 访问好友

```json
{
    "name": "访问好友",
    "type": "Visit",
    "params": {}
}
```

## 预设任务列表

| 文件 | 说明 |
|-----|------|
| `startup.json` | 只启动游戏 |
| `daily.json` | 日常任务 (启动+基建+1-7+访问+商店) |
| `fight.json` | 只刷副本 |
| `infrast_only.json` | 只基建换班 |
| `full.json` | 完整日常 (包含招募和领奖) |
| `roguelike.json` | 集成战略 |
