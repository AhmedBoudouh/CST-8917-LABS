# CST8917 - Assignment 1: Serverless Computing Critical Analysis

**Student Name:** Ahmed Boudouh  
**Student Number:** 041162807  
**Course:** CST8917 - Serverless Applications  
**Assignment:** Serverless Computing - Critical Analysis  


---

## Part 1: Paper Summary

The paper "Serverless Computing: One Step Forward, Two Steps Back" by Hellerstein et al. (2019) presents a critical evaluation of first-generation serverless computing platforms, particularly Functions-as-a-Service (FaaS) offerings like AWS Lambda. The central thesis is captured in the title: while serverless computing represents progress through autoscaling and pay-as-you-go billing models (one step forward), it simultaneously introduces significant limitations that hinder data-centric and distributed computing (two steps back).

The "one step forward" refers to the autoscaling capability that automatically allocates and deallocates resources based on workload demand. This eliminates the need for developers to provision servers, monitor services, or write custom scaling scripts. The "two steps back" refers to how current FaaS platforms ignore efficient data processing and stymie distributed systems development—precisely the domains driving modern computing innovation.

The authors identify several critical limitations in first-generation serverless platforms. First, **execution time constraints**: AWS Lambda functions were limited to 15-minute lifetimes, forcing stateless design patterns. Second, **I/O bottlenecks**: Lambda functions achieved only 538Mbps network bandwidth on average—an order of magnitude slower than modern SSDs—with bandwidth decreasing proportionally as compute scaled up. Third, **communication through slow storage**: Functions cannot directly address each other network-wise, forcing communication through storage intermediaries like S3 or DynamoDB, which the authors demonstrate is 372× slower than direct networking for 1KB messages. Fourth, **no specialized hardware access**: FaaS offerings only provided CPU hyperthreads and RAM, with no GPU or accelerator support, limiting machine learning and scientific computing workloads. Fifth, **the data-shipping anti-pattern**: FaaS routinely moves data to code rather than code to data, violating fundamental database principles about memory hierarchy and locality.

The authors propose several characteristics for future cloud programming environments. First, **fluid code and data placement**: infrastructure should support shipping code to data while maintaining logical separation for elasticity. Second, **heterogeneous hardware support**: developers should access specialized hardware through high-level DSLs with cost-effective compilation. Third, **long-running, addressable virtual agents**: programmers need persistent, named endpoints that survive across requests, similar to actors or tuplespaces, but virtually remapped across physical resources. Fourth, **disorderly programming**: languages should encourage small, granular units of computation and data that move easily across time and space, embracing asynchronous, coordination-free patterns.

---

## Part 2: Azure Durable Functions Deep Dive

### Orchestration Model

Azure Durable Functions extends basic Azure Functions with three distinct function types: orchestrator functions, activity functions, and client functions. The **client function** initiates orchestration via HTTP triggers, queues, or timers. The **orchestrator function** defines workflow logic using imperative code with `await` (C#) or `yield` (JavaScript/Python) operators, calling activity functions in sequence or parallel. The **activity functions** perform actual work like API calls or database operations. This differs fundamentally from basic FaaS where each function invocation is isolated and stateless. In Durable Functions, the orchestrator maintains workflow state across multiple function executions, enabling complex coordination patterns like function chaining and fan-out/fan-in that basic FaaS cannot express without external state management systems.

### State Management

Durable Functions addresses the paper's criticism of stateless functions through **event sourcing and checkpointing**. Instead of storing current state directly, the Durable Task Framework records an append-only history of all actions (activity calls, timers, events) to Azure Storage. When an orchestrator reaches an `await` call, it checkpoints progress and can be unloaded from memory. Upon waking, it replays execution from the beginning, using the history to skip completed activities and restore local state. This provides durable state management without requiring developers to implement custom persistence logic. The orchestration history table stores complete audit trails, enabling reliable compensation actions and reconstruction of state at any point.

### Execution Timeouts

Durable Functions partially addresses timeout limitations through **asynchronous orchestration patterns**. While regular Azure Functions on Consumption plans face 5-10 minute execution limits, orchestrator functions can run for days or weeks because they yield control at each `await` point and resume via storage triggers. However, this solution is architectural rather than eliminating limits: **activity functions** still face the same timeout constraints as regular functions (5-10 minutes on Consumption, up to 60 minutes on Premium, or unlimited on Dedicated plans with Always On enabled). The orchestrator itself has no timeout, but the individual work units (activities) remain constrained by their hosting plan's limits.

### Communication Between Functions

Durable Functions improves upon basic FaaS communication patterns but does not fully resolve the storage-intermediary limitation. Orchestrators communicate with activities through **internal queues and storage tables** (Azure Table Storage by default), not direct network addressing. When an orchestrator calls an activity, it drops a message into a queue; a worker VM picks up the message, executes the activity, and returns results via another queue. While this abstracts away manual queue management, it still relies on storage intermediaries rather than direct point-to-point networking. The paper's finding that storage-based communication is 372× slower than direct networking remains relevant—Durable Functions optimizes the developer experience but not the underlying network topology.

### Parallel Execution (Fan-Out/Fan-In)

The fan-out/fan-in pattern directly addresses the paper's concern about distributed computing limitations. Developers can schedule multiple activity functions in parallel using `Task.WhenAll` (C#) or `context.df.Task.all` (JavaScript), and the framework automatically tracks completion without manual bookkeeping. For example, processing thousands of Excel rows can be parallelized across multiple VMs by splitting data into chunks and invoking activity functions concurrently. The orchestrator aggregates results when all parallel tasks complete. However, this remains **uncoordinated parallelism**—the paper's criticism about lacking fine-grained communication for leader election, consensus protocols, or transaction coordination remains unresolved. Durable Functions excels at embarrassingly parallel workloads but does not enable the sophisticated distributed protocols the authors highlight as essential.

---

## Part 3: Critical Evaluation

### Limitations That Remain Unresolved

**First, specialized hardware access remains unavailable.** Azure Functions, including Durable Functions, does not support GPU acceleration or custom hardware. The paper emphasizes that hardware specialization is accelerating, with GPUs essential for deep learning and accelerators for database processing. While Azure offers GPU-enabled VMs (NV-series), these are not accessible through the Functions serverless model—developers must use container instances or Kubernetes for such workloads. This limitation significantly constrains machine learning inference and training scenarios that the paper identifies as critical modern workloads.

**Second, the data-shipping architecture persists.** Durable Functions still operates on the principle of moving data to code rather than code to data. Activity functions execute on separate VMs from data storage, and the orchestrator replays history by re-executing code rather than maintaining persistent memory structures. The paper argues that "memory hierarchy realities—across various storage layers and network delays—make this a bad design decision." While Durable Functions adds checkpointing and replay semantics, it does not implement the "fluid code and data placement" the authors envision, where the infrastructure intelligently co-locates computation with data to minimize network transfers.

### Verdict

Azure Durable Functions represents **partial progress toward the authors' vision**—it solves the state management and workflow orchestration problems effectively, but does not fundamentally address the hardware and data-locality limitations.

On the positive side, Durable Functions delivers exactly the kind of "long-running, addressable virtual agents" the authors propose. Orchestrators are virtual entities with stable identities that persist across time, dynamically remapped across physical VMs, with automatic state reconstruction. The fan-out/fan-in pattern and event-sourcing approach demonstrate that higher-level abstractions can make distributed programming more accessible without sacrificing reliability.

However, Durable Functions works **around** fundamental limitations rather than solving them. It accepts the constraint that functions cannot directly address each other and builds reliable queues on top of storage services. It accepts hardware homogeneity and focuses on orchestration rather than computation. The paper warns that current serverless infrastructure "locks users into either using proprietary provider services or maintaining their own servers"—Durable Functions, while open-source in its programming model, still ties users to Azure's storage and compute infrastructure with the same economic and technical lock-in concerns.

The authors envisioned a future where "cloud programmers need to be able to harness the compute power and storage capacity of the cloud in an autoscaling, cost-efficient manner" with "fluid code and data placement" and "heterogeneous hardware support." Durable Functions achieves the autoscaling and cost-efficiency goals for workflow orchestration but maintains the separation of compute and storage that the paper identifies as problematic. It is a significant improvement over basic FaaS for stateful workflows, but it does not represent the architectural transformation the authors argue is necessary for true cloud-scale innovation.

---

## References

1. Hellerstein, J. M., et al. (2019). *Serverless Computing: One Step Forward, Two Steps Back*. CIDR 2019. https://www.cidrdb.org/cidr2019/papers/p119-hellerstein-cidr19.pdf

2. Microsoft Learn. (2025). *Durable Orchestrations - Azure Functions*. https://learn.microsoft.com/en-us/azure/azure-functions/durable/durable-functions-orchestrations

3. Keyhole Software. (2025). *Long-Running Workflows Made Simple with C# + Azure Durable Functions*. https://keyholesoftware.com/long-running-workflows-made-simple-with-c-azure-durable-functions/

4. Microsoft Learn. (2025). *Durable Functions Overview - Azure*. https://learn.microsoft.com/en-us/azure/azure-functions/durable/durable-functions-overview

5. Microsoft Learn. (2025). *Azure Functions Scale and Hosting*. https://learn.microsoft.com/en-us/azure/azure-functions/functions-scale

6. Medium - Robert Dennyson. (2024). *The Ultimate Guide to Azure Durable Functions*. https://medium.com/@robertdennyson/the-ultimate-guide-to-azure-durable-functions-a-deep-dive-into-long-running-processes-best-bacc53fcc6ba

7. Microsoft Learn. (2025). *Durable Functions Overview - Azure*. https://learn.microsoft.com/en-us/azure/azure-functions/durable/durable-functions-overview

8. Turbo360. (2018). *Azure Durable Functions and its Key Concepts*. https://turbo360.com/blog/introduction-to-azure-durable-functions

9. Microsoft Learn Q&A. (2024). *How can I increase the timeout on my durable function app?* https://learn.microsoft.com/en-us/answers/questions/1843853/how-can-i-increase-the-timeout-on-my-durable-funct

10. Systems Architect. (n.d.). *Need for GPU or specialized hardware acceleration*. https://www.systemsarchitect.io/services/azure-functions/seek-alternatives-if-you-need/pt/need-for-gpu-or-specialized-hardware-acceleration

11. DZone. (2023). *Azure Durable Functions: Fan-Out/Fan-In Pattern*. https://dzone.com/articles/azure-durable-functions-fan-outfan-in-pattern

12. Build5Nines. (2024). *Azure Functions: Extend Execution Timeout Past 5 Minutes*. https://build5nines.com/azure-functions-extend-execution-timeout-past-5-minutes/

---

## AI Disclosure Statement

AI tools were used to assist with this assignment. Specifically, AI was used to help structure the analysis and ensure comprehensive coverage of the paper's arguments. All technical claims about Azure Durable Functions were verified against official Microsoft documentation and technical articles. The critical evaluation and final verdict represent original analysis based on the research conducted.