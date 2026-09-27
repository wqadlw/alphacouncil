-- 0002 · market_cache：行情结果的磁盘缓存（spec 006）
--
-- 为什么这张表存在：MemoryCache 的存活域是进程内存，应用一重启，
-- "全源失败时回退到上一个有效值（标 stale）"就无米下锅。这张表把
-- 那份"上一个有效值"放进与应用数据同一个 SQLite 文件里，重启后仍在。
--
-- 为什么它和用户数据同库：缓存行是纯可再生数据（丢了就丢，重新取即可），
-- 量级是个位数标的 × 两个数据集；为它单开一个存储机制（独立文件/新依赖）
-- 违背"先复用既有设施"（宪法 2.1 #3）。
--
-- 列的最小集：payload 是完整的 DataResult JSON（source / fetched_at / reason
-- 都在里面——**不另立列重复存**，两份真相会漂移）；expires_at 是 Unix 墙钟秒
-- （**不能用 monotonic**——它的纪元不跨进程，重启后 TTL 判定全部失真）；
-- dataset 让读取侧可以按类型严格重建载荷，不靠解析 key 字符串猜。
--
-- 过期行不做后台清理：同 key 写入即覆盖，量级不需要 GC。
-- 回滚：表里只有可再生缓存，DROP 无损，destructive_down = false。

CREATE TABLE market_cache (
    cache_key  TEXT NOT NULL PRIMARY KEY,
    dataset    TEXT NOT NULL,
    payload    TEXT NOT NULL,
    expires_at REAL NOT NULL,
    CONSTRAINT market_cache_key_required_check
        CHECK (length(trim(cache_key)) > 0),
    CONSTRAINT market_cache_dataset_check
        CHECK (dataset IN ('realtime', 'daily')),
    CONSTRAINT market_cache_payload_required_check
        CHECK (length(trim(payload)) > 0),
    CONSTRAINT market_cache_payload_json_check
        CHECK (json_valid(payload))
) STRICT;
