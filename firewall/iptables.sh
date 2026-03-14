# 0) Block moltbook and clawhub

sudo iptables -A OUTPUT -p tcp -d moltbook.com -j REJECT
sudo iptables -A OUTPUT -p udp -d moltbook.com -j REJECT
sudo iptables -A OUTPUT -p tcp -d clawhub.io -j REJECT
sudo iptables -A OUTPUT -p udp -d clawhub.io -j REJECT

# 1) Allow established connections FIRST (keeps your current session alive)
iptables -I INPUT 1 -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT

# 2) Allow loopback
iptables -I INPUT 2 -i lo -j ACCEPT

# 3) Allow your LAN subnet (this guarantees you keep access over the same network you are (within your modem)
NET=$(ip -o -f inet addr show $(ip route show default | awk '{print $5}') | awk '{print $4}')
PREFIX=$(echo $NET | cut -d/ -f1 | awk -F. '{print $1"."$2"."$3".0"}')
MASK=$(echo $NET | cut -d/ -f2)

sudo iptables -I INPUT 3 -s $PREFIX/$MASK -j ACCEPT

# 4) Only now drop everything else by default
iptables -P INPUT DROP
iptables -P FORWARD DROP
iptables -P OUTPUT ACCEPT

# 5) Persist rules
sudo netfilter-persistent save