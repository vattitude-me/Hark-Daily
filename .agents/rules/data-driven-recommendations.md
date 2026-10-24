# Data-Driven System Analysis & Pros/Cons Before Recommendations

Before recommending or executing any infrastructure, data-pipeline, performance, or architectural approach:

1. **Profile End-to-End First (No Blind Recommendations)**:
   - Gather concrete baseline metrics across the entire chain before proposing a change:
     - Storage & filesystem type (`findmnt`, `df -h`, SSD vs. HDD, native `ext4`/`APFS` vs. FUSE `mount.ntfs`).
     - Compute & memory limits (`nproc`, CPU model, RAM/swap, active container limits).
     - Network & protocol constraints (bandwidth, session/cookie TTLs, API call overhead per item).
     - Existing service intermediaries (e.g., proxies, optimizers, background workers).

2. **Present Measured Pros, Cons, and End-to-End Time Estimates**:
   - Never recommend changing a running pipeline without calculating:
     - **Current measured throughput & ETA** vs. **projected throughput & ETA** of each option.
     - **Cost of switching** (e.g., lost progress, re-scanning overhead, disk thrashing).
     - **Pros, Cons, and Risks** backed by actual test data from a small sample (e.g., 10–50 items) before touching a multi-gigabyte batch.

3. **Respect Running Progress**:
   - Do not interrupt or restart long-running jobs to test a flag change unless explicitly approved after showing the exact trade-off.
