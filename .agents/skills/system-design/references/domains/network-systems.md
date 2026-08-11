# Network and Service Topology

Use for networked system design, enterprise or homelab topology, service edge, routing, segmentation, DNS, VPN, load balancing, ingress/egress, and connectivity architecture.

## First Questions

- What sites, regions, networks, tenants, environments, or trust zones exist?
- What traffic must flow between them, and what must be blocked?
- What latency, bandwidth, redundancy, compliance, and operations constraints exist?
- Who manages routing, DNS, certificates, firewalls, VPNs, and change windows?
- What hardware/cloud/network services already exist?

## Design Surfaces

- Topology: sites, regions, VPC/VNet, subnets, VLANs, gateways, firewalls, load balancers.
- Addressing: CIDR plan, overlap checks, reserved ranges, growth.
- Routing: static, BGP, OSPF, transit gateways, peering, service discovery.
- Segmentation: tenant, environment, management, workload, IoT/guest, PCI/regulated zones.
- Edge: DNS, CDN, WAF, API gateway, ingress controller, TLS termination.
- Remote access: VPN, zero trust access, bastion, just-in-time admin.
- Observability: flow logs, interface health, synthetic probes, DNS/route monitoring.
- Change safety: pre-deployment validation, rollback, maintenance window, blast radius.

## Architecture Rules

- Segmentation without firewall/ACL rules is not security.
- Management plane must be separated and more restricted than workload traffic.
- DNS and certificate ownership are architecture decisions for externally reachable systems.
- Route tables and security rules need explicit owner and validation.
- Redundancy must be tested, not only drawn.
- Avoid overlapping CIDRs when future peering, VPN, or merger/integration is plausible.

## Validation Before Change

Before network or edge changes, verify:

| Area | Check |
| --- | --- |
| Addressing | CIDR overlap, reserved ranges, future growth, peering/VPN constraints |
| Routing | Route table intent, asymmetric routing, failover path, blackhole risk |
| Segmentation | Allow/deny matrix, firewall rule ownership, management-plane isolation |
| Edge | DNS TTL, certificate ownership, WAF/CDN behavior, health checks |
| Rollback | Exact revert steps, change window, blast radius, monitoring signal |

Network diagrams are not enough; include validation commands or operator checks where possible.

## Review Smells

- Flat network for workloads with different trust levels.
- Public admin endpoints.
- Native/untagged VLAN equals management VLAN.
- No route or subnet overlap validation.
- Single DNS, NAT, VPN, gateway, or firewall with no recovery plan.
- Load balancer health checks test process health but not dependency readiness.
- No rollback for network config changes.

## Expected Outputs

- Network topology diagram.
- Addressing and segmentation table.
- Traffic allow/deny matrix.
- Routing and DNS plan.
- Edge and certificate ownership.
- Operational validation and rollback plan.
- ADR candidates for segmentation model, connectivity pattern, ingress/egress architecture, and remote access model.
