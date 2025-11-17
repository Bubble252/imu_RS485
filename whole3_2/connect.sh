#!/bin/bash
# 连接到目标服务器

# 使用本地目录的密钥文件
ssh -i ./capri_yhx_2237 -p 2237 \
  -o "ProxyCommand ssh -i ./leo_tmp_2258.txt -p 2258 -W %h:%p root@202.112.113.78" \
  root@202.112.113.74
