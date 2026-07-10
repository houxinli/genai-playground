# logging/ — 日志

只有 `logger.py::get_logger(name, log_file=None, level=INFO)`:控制台必开,传 `log_file` 时追加文件 handler;同名 logger 二次获取直接复用,不会重复挂 handler——**副作用是第二次传入不同 `log_file` 会被忽略**,想分文件就用不同的 logger name。

包名与标准库 `logging` 同名,但全项目用 `tasks.ytmusic.src.logging.logger` 绝对导入,不冲突;不要在这个包里加相对导入或 `import logging` 之外的花样。
