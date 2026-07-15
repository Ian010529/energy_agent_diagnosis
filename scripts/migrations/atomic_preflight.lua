local expected = {"hash", "hash", "zset", "stream"}

for index, key in ipairs(KEYS) do
  local actual = redis.call("TYPE", key).ok
  if actual ~= "none" and actual ~= expected[index] then
    return {0, "KEY_TYPE_MISMATCH", index, expected[index], actual}
  end
end

redis.call("HSET", KEYS[1], "revision", ARGV[1], "active_run_id", ARGV[2])
redis.call("HSET", KEYS[2], "status", "ACCEPTED", "payload_hash", ARGV[3])
redis.call("ZADD", KEYS[3], ARGV[4], ARGV[2])
redis.call("XADD", KEYS[4], "*", "event_type", "run.accepted", "run_id", ARGV[2])
return {1, "OK"}
