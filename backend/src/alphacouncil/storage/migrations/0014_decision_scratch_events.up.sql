-- 0014 · 「这条是试验记录」—— ⭐⭐ 一张只增的事件表，⭐⭐ 当前状态 = 最后一行
--
-- ⭐⭐ spec 060 §一之补。⭐⭐ **这份注释里的每个「实测」都是 2026-10-06 量出来的，**
-- ⭐⭐ 而第一版 spec 里三句关于「先例」的说法有两句是错的 —— ⭐⭐ 详见那一节。

CREATE TABLE decision_scratch_events (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,

  -- ⭐⭐ 不声明外键，⭐⭐ 而且这是**故意的**：⭐⭐ `reviews` 与 `decision_review_state`
  -- ⭐⭐ 都声明了 `ON DELETE CASCADE` 到 `decisions`，⭐⭐ 而**级联删掉读者自己按下的
  -- ⭐⭐ 标记，比删掉一条决策更糟** —— 标记是**他的动作**，⭐⭐ 不是派生数据。
  -- ⭐⭐
  -- ⭐⭐ **代价要说清，⭐⭐ 而它不是零：** `D-25` 扫的是**已声明**的外键，
  -- ⭐⭐ **所以它看不见这张表。** ⭐⭐ 父行缺失只能来自删除决策，⭐⭐ 而
  -- ⭐⭐ `grep 'DELETE FROM decisions'` **零命中**（量过两次：spec 060 与其之补）。
  -- ⭐⭐ 若将来真的有了删除路径，⭐⭐ 这里是第一个要加守卫的地方。
  decision_id  TEXT NOT NULL,

  -- ⭐⭐ 受约束的动词枚举，⭐⭐ 照 `watchlist_events.kind` 的形状 ⭐⭐
  -- ⭐⭐ （那是本仓真正的先例：⭐⭐ 只增事件表 + 受约束动词 + 状态由日志推导）。
  -- ⭐⭐ **不做 `supersedes_id`：** ⭐⭐ 它在 `watchlist` 里成立是因为
  -- ⭐⭐ 「改理由」天然指向一条被改的行；⭐⭐ 而「标记 / 取消」是**两个动词的状态**，
  -- ⭐⭐ **没有任何读者会问「这次取消取代了哪一次标记」。** ⭐⭐
  -- ⭐⭐ 链不增加一个读者，只增加一个引用完整性面；⭐⭐ 而**日志本身
  -- ⭐⭐ 已经回答了「谁取消的」—— 所有行都在那里。** ⭐⭐
  verb         TEXT NOT NULL,

  recorded_at  TEXT NOT NULL,

  CONSTRAINT decision_scratch_verb_check
    CHECK (verb IN ('marked', 'unmarked')),

  -- ⭐⭐ 与 `decisions.id` 同一形状，⭐⭐ 所以「这不是一条决策」由数据库拒绝，⭐⭐
  -- ⭐⭐ 而不是等到界面上才发现。
  CONSTRAINT decision_scratch_decision_shape_check
    CHECK (length(trim(decision_id)) > 0),

  CONSTRAINT decision_scratch_recorded_at_check
    CHECK (strftime('%Y-%m-%dT%H:%M:%fZ', recorded_at) = recorded_at)
) STRICT;

-- ⭐⭐ 只增：⭐⭐ 与 `decisions` / `watchlist_events` 同一形状。⭐⭐
-- ⭐⭐ **`S-04 check-append-only-triggers` 要求这一对触发器存在，⭐⭐** ⭐⭐
-- ⭐⭐ 而它的**理由不是本表特别，⭐⭐ 是「取消标记」必须是一行，⭐⭐
-- ⭐⭐ 而不能是把 `verb` 改回去（覆盖）或删掉那行（删除）。** ⭐⭐
CREATE TRIGGER decision_scratch_events_no_update
BEFORE UPDATE ON decision_scratch_events
BEGIN SELECT RAISE(ABORT, 'decision_scratch_events is append-only: the state is the last row, not an edit'); END;

CREATE TRIGGER decision_scratch_events_no_delete
BEFORE DELETE ON decision_scratch_events
BEGIN SELECT RAISE(ABORT, 'decision_scratch_events is append-only: the rows are the record'); END;

-- ⭐⭐ `state` 是本表的**当前状态**：⭐⭐ 最后一个动词是 `marked` 的那些。
-- ⭐⭐ **没有这一列，⭐⭐ 每个读它的查询都得重复一遍「取最后一行」，⭐⭐
-- ⭐⭐ 而那正是会走样的地方** —— ⭐⭐ `D-25` 上一版的 bug 就是
-- ⭐⭐「复合键被当成两个引用」，⭐⭐ 同一个形状：⭐⭐
-- ⭐⭐ 读法一旦重复，⭐⭐ 总会有一处重复错。⭐⭐
-- ⭐⭐ 它是**派生**的，⭐⭐ 就像 `decision_review_state` 之于 `reviews`。⭐⭐
CREATE INDEX decision_scratch_events_by_decision
  ON decision_scratch_events (decision_id, id);