### Launch Brief: Document Compare Feature

#### 1. Executive Summary
The Document Compare feature is designed to streamline the review process for legal documents, enabling users to quickly identify changes between versions. By providing a native diff engine within Genie’s real-time editor, this feature addresses significant pain points for founders and executives who often struggle with tedious document comparisons.

#### 2. Customer Insights
- **Pain Points:**
  - Manual scrolling between documents is time-consuming and frustrating ("I hate manually scrolling between two Word docs").
  - Difficulty in understanding changes without legal expertise ("Redlines are a nightmare when you’re not a lawyer").
  - Need for quick sharing of changes with colleagues ("Sometimes I just need to share the changes with my cofounder quickly").

- **Desired Outcomes:**
  - Instant visibility of changes without needing to read everything again ("I just want to see what changed, not read everything again").
  - A more efficient review process to save time and reduce reliance on legal counsel ("This would save me from begging our counsel to check every clause").

#### 3. Product & Engineering Details
- **Scope:** 
  - Native diff engine built into Genie’s editor, allowing comparison of Genie docs and external files (DOCX, PDFs).
  - Outputs include side-by-side and unified diff views.

- **Status:** 
  - Currently in beta (Version 0.9).

- **Differentiators:**
  - Integrated feature, not reliant on third-party plugins, enhancing user experience and trust.
  - AI integration planned for future enhancements to summarize changes and flag risky clauses.

- **Blockers:**
  - Unreliable PDF extraction and performance degradation with documents over 100 pages.
  - False conflicts due to parallel edits, requiring improvements in locking mechanisms.

#### 4. Messaging Pillars & Proof Points
- **Time-Saving:** "Instant redlines, effortless review" allows users to focus on what matters.
- **User Trust:** Deterministic output ensures legal reliability—"same input always = same output."
- **Enhanced Collaboration:** Share clean, unified redlines easily, facilitating better communication with investors and counterparties.

#### 5. Launch Risks / Open Questions
- Reliability of PDF extraction and handling of large documents (>100 pages).
- Clarity on how to position the upcoming AI features without cannibalizing existing products.
- Confirmation of metrics for success post-launch (e.g., % of Pro Plan companies using Compare 2+ times per week).

#### 6. Recommended Next Steps
- **Marketing:**
  - Develop launch content emphasizing time savings and user trust.
  - Prepare a blog post highlighting the feature and its benefits, including a "coming soon" note on AI enhancements.

- **Product:**
  - Address known issues related to PDF extraction and performance.
  - Finalize the user interface for the AI summary sidebar for future iterations.

- **Engineering:**
  - Focus on improving the operational transform layer to reduce false conflicts.
  - Ensure robust testing for performance at scale and reliability of outputs. 

This brief synthesizes insights from multiple sources, ensuring alignment across teams for a successful launch of the Document Compare feature.
