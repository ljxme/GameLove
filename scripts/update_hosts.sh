#!/bin/bash
set -e

HOSTS_DIR="../hosts"
STEAM_DOMAINS=("store.steampowered.com" "steamcommunity.com" "cdn.cloudflare.steamstatic.com")
EPIC_DOMAINS=("www.epicgames.com" "launcher-public-service-prod06.ol.epicgames.com" "epicgames-download1.akamaized.net")

test_latency() {
  ip=$1
  ping -c 2 -w 2 $ip > /dev/null 2>&1
  if [ $? -eq 0 ]; then
    ping -c 2 $ip | tail -1 | awk -F '/' '{print $5}'
  else
    echo 9999
  fi
}

generate_hosts() {
  domains=("${!1}")
  output_file=$2
  echo "# Generated hosts - $(date)" > "$output_file"

  for domain in "${domains[@]}"; do
    ips=$(dig +short $domain)
    best_ip=""
    lowest=9999
    for ip in $ips; do
      latency=$(test_latency $ip)
      if (( $(echo "$latency < $lowest" | bc -l) )); then
        lowest=$latency
        best_ip=$ip
      fi
    done
    if [ -n "$best_ip" ]; then
      echo "$best_ip $domain" >> "$output_file"
    fi
  done
}

mkdir -p $HOSTS_DIR
generate_hosts STEAM_DOMAINS[@] "$HOSTS_DIR/steam_hosts"
generate_hosts EPIC_DOMAINS[@] "$HOSTS_DIR/epic_hosts"

echo "Hosts files generated successfully!"
