from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dataio.jsonl_loader import load_jsonl_models
from evaluation.retrieval.contracts_v2 import (
    RetrievalEvaluationCaseV2,
    RetrievalEvaluationGoldV2,
    RetrievalRuntimeContextV2,
    validate_retrieval_case_feasibility_v2,
)
from evaluation.retrieval.dataset import load_retrieval_evaluation_cases
from evaluation.retrieval.models import RetrievalEvaluationCase
from evaluation.retrieval.storage import (
    diff_json_objects,
    load_json_record,
    load_jsonl_records,
    write_many_atomic,
)
from knowledge_base import (
    KnowledgeChunk,
    KnowledgeChunkV2,
    KnowledgeDocument,
    KnowledgeDocumentV2,
    SolutionScopeType,
    SolutionScopeV2,
    chunk_content_projection_v1,
    content_projection_hash,
    document_content_projection_v1,
    load_demo_solution_scope,
    load_knowledge_chunks,
    load_knowledge_documents,
    load_knowledge_manifest,
    validate_chunk_scope_against_document_v2,
)

V1_DOCUMENTS_PATH = Path("data/knowledge_base/documents.v1.jsonl")
V1_CHUNKS_PATH = Path("data/knowledge_base/chunks.v1.jsonl")
V1_MANIFEST_PATH = Path("data/knowledge_base/manifest.v1.json")
V1_SCOPE_PATH = Path("data/knowledge_base/demo_solution_scope.v1.json")
V1_CASES_PATH = Path("data/evaluation/retrieval/retrieval_cases.v1.jsonl")
V1_LEXICAL_RESULTS_PATH = Path("data/evaluation/retrieval/lexical_baseline_results.v1.jsonl")
V1_LEXICAL_SUMMARY_PATH = Path("data/evaluation/retrieval/lexical_baseline_summary.v1.json")
V1_VECTOR_RESULTS_PATH = Path("data/evaluation/retrieval/vector_baseline_results.v1.jsonl")
V1_VECTOR_SUMMARY_PATH = Path("data/evaluation/retrieval/vector_baseline_summary.v1.json")
V1_HYBRID_RESULTS_PATH = Path("data/evaluation/retrieval/hybrid_baseline_results.v1.jsonl")
V1_HYBRID_SUMMARY_PATH = Path("data/evaluation/retrieval/hybrid_baseline_summary.v1.json")
V1_METHOD_COMPARISON_PATH = Path("data/evaluation/retrieval/retrieval_method_comparison.v1.json")
V1_FAILURE_ANALYSIS_PATH = Path("data/evaluation/retrieval/retrieval_failure_analysis.v1.json")
V1_MIGRATION_PLAN_PATH = Path("data/evaluation/retrieval/retrieval_v2_migration_plan.json")

V2_SCOPE_MIGRATION_PATH = Path("data/knowledge_base/solution_scope_migration.v2.json")
V2_DOCUMENTS_PATH = Path("data/knowledge_base/documents.v2.jsonl")
V2_CHUNKS_PATH = Path("data/knowledge_base/chunks.v2.jsonl")
V2_MANIFEST_PATH = Path("data/knowledge_base/manifest.v2.json")
V2_CASE_MIGRATION_PATH = Path("data/evaluation/retrieval/retrieval_case_migration.v2.json")
V2_CASES_PATH = Path("data/evaluation/retrieval/retrieval_cases.v2.jsonl")
V2_FEASIBILITY_PATH = Path("data/evaluation/retrieval/retrieval_case_feasibility.v2.json")
V2_CONFIG_PATH = Path("data/evaluation/retrieval/retrieval_benchmark_config.v2.json")

BUILD_TOOL_VERSION = "retrieval_benchmark_v2_builder_v1"
KB_CONTRACT_VERSION = "v2"
RETRIEVAL_CONTRACT_VERSION = "v2_method_aware"
FAILURE_TAXONOMY_VERSION = "v2_method_aware"
BOUNDARY_CONTRACT_VERSION = "v2"
BENCHMARK_VERSION = "retrieval_benchmark_v2"
EVALUATION_DATE = "2026-06-29"
TOP_K = 5

FROZEN_V1_PATHS: dict[str, Path] = {
    "documents_v1": V1_DOCUMENTS_PATH,
    "chunks_v1": V1_CHUNKS_PATH,
    "manifest_v1": V1_MANIFEST_PATH,
    "demo_scope_v1": V1_SCOPE_PATH,
    "retrieval_cases_v1": V1_CASES_PATH,
    "lexical_results_v1": V1_LEXICAL_RESULTS_PATH,
    "lexical_summary_v1": V1_LEXICAL_SUMMARY_PATH,
    "vector_results_v1": V1_VECTOR_RESULTS_PATH,
    "vector_summary_v1": V1_VECTOR_SUMMARY_PATH,
    "hybrid_results_v1": V1_HYBRID_RESULTS_PATH,
    "hybrid_summary_v1": V1_HYBRID_SUMMARY_PATH,
    "method_comparison_v1": V1_METHOD_COMPARISON_PATH,
    "failure_analysis_v1": V1_FAILURE_ANALYSIS_PATH,
    "migration_plan_v1": V1_MIGRATION_PLAN_PATH,
}

DOCUMENT_SCOPE_OVERRIDES: dict[str, dict[str, Any]] = {
    "KB-CAP-001": {
        "target_scope_type": "multi_solution",
        "primary_solution_id": "合规政策RAG检索助手",
        "applicable_solution_ids": ["合规政策RAG检索助手", "客服辅助回复方案"],
        "excluded_solution_ids": [],
        "scope_notes": "Citation-visible answer support spans compliance retrieval and assistive customer-service reply.",
        "migration_reason": "Shared answer-with-citation capability remains multi-solution, not global.",
        "decision_source": "Document title, summary, and chunk content explicitly reference both cited reply scenarios.",
    },
    "KB-CAP-002": {
        "target_scope_type": "multi_solution",
        "primary_solution_id": "客户身份统一与数据集成方案",
        "applicable_solution_ids": ["客户身份统一与数据集成方案", "商品知识库RAG方案", "服务工单系统集成方案"],
        "excluded_solution_ids": [],
        "scope_notes": "Deprecated context-assembly capability remains limited to the three workflow solutions it names.",
        "migration_reason": "The document is shared across three named solutions, but does not apply to all six demo solutions.",
        "decision_source": "Document content explicitly references customer identity, product knowledge, and work-order context together.",
    },
    "KB-CASE-001": {
        "target_scope_type": "multi_solution",
        "primary_solution_id": "商品知识库RAG方案",
        "applicable_solution_ids": ["商品知识库RAG方案", "客服辅助回复方案"],
        "excluded_solution_ids": [],
        "scope_notes": "Synthetic retail case study remains limited to product knowledge and assistive reply.",
        "migration_reason": "The case study narrates a paired rollout for product knowledge and service reply assistance.",
        "decision_source": "Document title and content explicitly pair retail knowledge governance with assistive reply use.",
    },
    "KB-CASE-002": {
        "target_scope_type": "multi_solution",
        "primary_solution_id": "客户身份统一与数据集成方案",
        "applicable_solution_ids": ["客户身份统一与数据集成方案", "服务工单系统集成方案"],
        "excluded_solution_ids": [],
        "scope_notes": "Synthetic service-operations case study remains limited to identity and work-order integration.",
        "migration_reason": "The case study is about the interaction between identity unification and work-order collaboration.",
        "decision_source": "Document title and both chunks explicitly name service-operation integration with customer identity.",
    },
    "KB-PLAY-001": {
        "target_scope_type": "multi_solution",
        "primary_solution_id": "客户身份统一与数据集成方案",
        "applicable_solution_ids": ["客户身份统一与数据集成方案", "服务工单系统集成方案"],
        "excluded_solution_ids": [],
        "scope_notes": "Implementation steps stay limited to identity integration plus service work-order integration.",
        "migration_reason": "The playbook coordinates two implementation streams and is not a universal policy document.",
        "decision_source": "Document title and chunk text explicitly reference key mapping plus work-order authority decisions.",
    },
    "KB-PLAY-002": {
        "target_scope_type": "multi_solution",
        "primary_solution_id": "合规政策RAG检索助手",
        "applicable_solution_ids": ["合规政策RAG检索助手", "私有化大模型部署方案"],
        "excluded_solution_ids": [],
        "scope_notes": "Implementation sequencing spans controlled compliance retrieval and private deployment only.",
        "migration_reason": "The playbook ties knowledge governance readiness to private deployment execution.",
        "decision_source": "Document title and content explicitly combine compliance retrieval controls with deployment sequencing.",
    },
    "KB-SEC-001": {
        "target_scope_type": "cross_cutting_requirement",
        "primary_solution_id": "合规政策RAG检索助手",
        "applicable_solution_ids": ["合规政策RAG检索助手", "私有化大模型部署方案"],
        "excluded_solution_ids": [],
        "scope_notes": "Security and compliance requirements apply across controlled retrieval and private deployment readiness.",
        "migration_reason": "The document defines shared control requirements rather than a standalone solution payload.",
        "decision_source": "Both chunks describe access control, logs, approvals, and high-risk escalation requirements shared by two solutions.",
    },
    "KB-DEL-001": {
        "target_scope_type": "cross_cutting_requirement",
        "primary_solution_id": "服务工单系统集成方案",
        "applicable_solution_ids": ["服务工单系统集成方案", "私有化大模型部署方案"],
        "excluded_solution_ids": [],
        "scope_notes": "Expired delivery constraints stay limited to service integration and private deployment delivery planning.",
        "migration_reason": "The document records historical delivery constraints across two named delivery-heavy solutions.",
        "decision_source": "Document title and chunks discuss delivery-state history for integration and deployment only.",
    },
    "KB-INT-001": {
        "target_scope_type": "cross_cutting_requirement",
        "primary_solution_id": "客户身份统一与数据集成方案",
        "applicable_solution_ids": ["客户身份统一与数据集成方案", "客服辅助回复方案"],
        "excluded_solution_ids": [],
        "scope_notes": "Integration requirements apply to customer identity unification feeding assistive service reply.",
        "migration_reason": "The document defines preconditions shared by identity integration and assistive reply usage.",
        "decision_source": "Chunk content links identity unification, cross-channel state, and assistive reply behavior.",
    },
    "KB-INT-002": {
        "target_scope_type": "cross_cutting_requirement",
        "primary_solution_id": "服务工单系统集成方案",
        "applicable_solution_ids": ["商品知识库RAG方案", "服务工单系统集成方案"],
        "excluded_solution_ids": [],
        "scope_notes": "Integration requirements apply to work-order workflow plus scoped product-knowledge retrieval.",
        "migration_reason": "The document describes the integration seam between work-order state and product knowledge filtering.",
        "decision_source": "Chunk content explicitly couples work-order fields with product-knowledge retrieval scope.",
    },
    "KB-COM-001": {
        "target_scope_type": "global_policy",
        "primary_solution_id": None,
        "applicable_solution_ids": [
            "合规政策RAG检索助手",
            "客户身份统一与数据集成方案",
            "商品知识库RAG方案",
            "客服辅助回复方案",
            "服务工单系统集成方案",
            "私有化大模型部署方案",
        ],
        "excluded_solution_ids": [],
        "scope_notes": "Global commercial boundary for the full public demo scope; not a six-solution mixed answer payload.",
        "migration_reason": "This document encodes demo-wide commercial rules and explicit no-auto-commitment policy.",
        "decision_source": "Document title and both chunks state that the rule applies across all six demo solutions.",
    },
    "KB-UNS-001": {
        "target_scope_type": "cross_cutting_requirement",
        "primary_solution_id": "合规政策RAG检索助手",
        "applicable_solution_ids": ["合规政策RAG检索助手", "客服辅助回复方案", "私有化大模型部署方案"],
        "excluded_solution_ids": [],
        "scope_notes": "Unsupported-scenario guidance spans controlled compliance retrieval, assistive reply, and private deployment.",
        "migration_reason": "The document defines explicit unsupported boundaries across three named solutions.",
        "decision_source": "Chunk text enumerates unsupported promises, legal judgments, and inferred security-control claims.",
    },
    "KB-READY-001": {
        "target_scope_type": "cross_cutting_requirement",
        "primary_solution_id": "商品知识库RAG方案",
        "applicable_solution_ids": ["商品知识库RAG方案", "合规政策RAG检索助手"],
        "excluded_solution_ids": [],
        "scope_notes": "Readiness requirements span product-knowledge governance and policy-knowledge governance.",
        "migration_reason": "The document defines shared knowledge-governance prerequisites for two retrieval-oriented solutions.",
        "decision_source": "Both chunks explicitly reference product knowledge plus policy knowledge governance and citation-chain readiness.",
    },
    "KB-READY-002": {
        "target_scope_type": "cross_cutting_requirement",
        "primary_solution_id": "客户身份统一与数据集成方案",
        "applicable_solution_ids": ["客户身份统一与数据集成方案", "服务工单系统集成方案", "私有化大模型部署方案"],
        "excluded_solution_ids": [],
        "scope_notes": "Delivery readiness spans identity integration, service integration, and private deployment preparation.",
        "migration_reason": "The document is a shared readiness gate for responsibility, interfaces, and deployment cadence.",
        "decision_source": "Chunk content explicitly references responsibility teams, interfaces, and deployment duties across three solutions.",
    },
}

CHUNK_SCOPE_OVERRIDES: dict[str, dict[str, Any]] = {
    "KB-CAP-001#chunk-000-4a0d2db10fea": {
        "inherits_document_scope": True,
        "target_scope_type": "multi_solution",
        "primary_solution_id": "合规政策RAG检索助手",
        "applicable_solution_ids": ["合规政策RAG检索助手", "客服辅助回复方案"],
        "excluded_solution_ids": [],
        "scope_notes": "The capability description spans cited compliance retrieval and assistive reply.",
        "migration_reason": "Chunk content explicitly serves both cited-answer scenarios.",
    },
    "KB-CAP-001#chunk-001-bcb4fc0bf316": {
        "inherits_document_scope": False,
        "target_scope_type": "solution_specific",
        "primary_solution_id": "合规政策RAG检索助手",
        "applicable_solution_ids": ["合规政策RAG检索助手"],
        "excluded_solution_ids": [],
        "scope_notes": "This acceptance chunk is narrowed to compliance retrieval because citation-chain and high-risk send control are the benchmarked compliance concern.",
        "migration_reason": "The chunk is reused for compliance requirement evaluation and must not carry unrelated assistive-reply scope into forbidden-boundary checks.",
    },
    "KB-CAP-002#chunk-000-8171eccaf5f9": {
        "inherits_document_scope": True,
        "target_scope_type": "multi_solution",
        "primary_solution_id": "客户身份统一与数据集成方案",
        "applicable_solution_ids": ["客户身份统一与数据集成方案", "商品知识库RAG方案", "服务工单系统集成方案"],
        "excluded_solution_ids": [],
        "scope_notes": "The capability overview remains shared across all three orchestration-related solutions.",
        "migration_reason": "Chunk content explicitly names identity, product knowledge, and work-order context assembly together.",
    },
    "KB-CAP-002#chunk-001-12c93bdaf623": {
        "inherits_document_scope": True,
        "target_scope_type": "multi_solution",
        "primary_solution_id": "客户身份统一与数据集成方案",
        "applicable_solution_ids": ["客户身份统一与数据集成方案", "商品知识库RAG方案", "服务工单系统集成方案"],
        "excluded_solution_ids": [],
        "scope_notes": "The deprecation boundary still belongs to the same three-solution context-assembly capability.",
        "migration_reason": "The deprecation note remains about the same three-solution orchestration pattern.",
    },
    "KB-CASE-001#chunk-000-d5868a3597d2": {
        "inherits_document_scope": True,
        "target_scope_type": "multi_solution",
        "primary_solution_id": "商品知识库RAG方案",
        "applicable_solution_ids": ["商品知识库RAG方案", "客服辅助回复方案"],
        "excluded_solution_ids": [],
        "scope_notes": "The case-study background stays shared between product knowledge and assistive reply.",
        "migration_reason": "Problem framing covers both knowledge-governance and assistive reply workflow.",
    },
    "KB-CASE-001#chunk-001-77cb36877788": {
        "inherits_document_scope": True,
        "target_scope_type": "multi_solution",
        "primary_solution_id": "商品知识库RAG方案",
        "applicable_solution_ids": ["商品知识库RAG方案", "客服辅助回复方案"],
        "excluded_solution_ids": [],
        "scope_notes": "The solution-and-limits case-study chunk remains shared across the paired rollout.",
        "migration_reason": "The chunk narrates the paired use of product knowledge retrieval and assistive reply.",
    },
    "KB-CASE-002#chunk-000-2c2107739c83": {
        "inherits_document_scope": True,
        "target_scope_type": "multi_solution",
        "primary_solution_id": "客户身份统一与数据集成方案",
        "applicable_solution_ids": ["客户身份统一与数据集成方案", "服务工单系统集成方案"],
        "excluded_solution_ids": [],
        "scope_notes": "The service-operations background stays shared across identity and work-order coordination.",
        "migration_reason": "Chunk content frames the joint service-operations problem for two solutions.",
    },
    "KB-CASE-002#chunk-001-036ea7b824d0": {
        "inherits_document_scope": True,
        "target_scope_type": "multi_solution",
        "primary_solution_id": "客户身份统一与数据集成方案",
        "applicable_solution_ids": ["客户身份统一与数据集成方案", "服务工单系统集成方案"],
        "excluded_solution_ids": [],
        "scope_notes": "The solution-and-limits case-study chunk remains shared across the two integration solutions.",
        "migration_reason": "Chunk content narrates the paired implementation outcome for identity and work-order integration.",
    },
    "KB-PLAY-001#chunk-000-0015819a0dd7": {
        "inherits_document_scope": True,
        "target_scope_type": "multi_solution",
        "primary_solution_id": "客户身份统一与数据集成方案",
        "applicable_solution_ids": ["客户身份统一与数据集成方案", "服务工单系统集成方案"],
        "excluded_solution_ids": [],
        "scope_notes": "Implementation steps remain shared across identity mapping and work-order authority setup.",
        "migration_reason": "Chunk content explicitly coordinates source-system mapping with work-order authority design.",
    },
    "KB-PLAY-001#chunk-001-e90933b01fb0": {
        "inherits_document_scope": True,
        "target_scope_type": "multi_solution",
        "primary_solution_id": "客户身份统一与数据集成方案",
        "applicable_solution_ids": ["客户身份统一与数据集成方案", "服务工单系统集成方案"],
        "excluded_solution_ids": [],
        "scope_notes": "Risk and delivery constraints remain shared across identity and work-order integration.",
        "migration_reason": "The rework risks stay coupled to both master-data ownership and work-order integration delivery.",
    },
    "KB-PLAY-002#chunk-000-b5afe84948ef": {
        "inherits_document_scope": True,
        "target_scope_type": "multi_solution",
        "primary_solution_id": "合规政策RAG检索助手",
        "applicable_solution_ids": ["合规政策RAG检索助手", "私有化大模型部署方案"],
        "excluded_solution_ids": [],
        "scope_notes": "Governance-first sequencing remains shared across compliance retrieval and private deployment.",
        "migration_reason": "Chunk content explicitly sequences knowledge governance before private deployment.",
    },
    "KB-PLAY-002#chunk-001-22fb4bafb8ba": {
        "inherits_document_scope": False,
        "target_scope_type": "solution_specific",
        "primary_solution_id": "私有化大模型部署方案",
        "applicable_solution_ids": ["私有化大模型部署方案"],
        "excluded_solution_ids": [],
        "scope_notes": "This delivery-risk chunk is narrowed to private deployment acceptance and maintenance readiness.",
        "migration_reason": "The chunk focuses on deployment acceptance, patching, and run-maintenance ownership, which are private-deployment-specific.",
    },
    "KB-SEC-001#chunk-000-f8c40d662005": {
        "inherits_document_scope": True,
        "target_scope_type": "cross_cutting_requirement",
        "primary_solution_id": "合规政策RAG检索助手",
        "applicable_solution_ids": ["合规政策RAG检索助手", "私有化大模型部署方案"],
        "excluded_solution_ids": [],
        "scope_notes": "Core security requirements remain shared across controlled retrieval and private deployment.",
        "migration_reason": "The chunk lists shared control requirements for both solutions.",
    },
    "KB-SEC-001#chunk-001-d88fdb994b4e": {
        "inherits_document_scope": True,
        "target_scope_type": "cross_cutting_requirement",
        "primary_solution_id": "合规政策RAG检索助手",
        "applicable_solution_ids": ["合规政策RAG检索助手", "私有化大模型部署方案"],
        "excluded_solution_ids": [],
        "scope_notes": "Escalation behavior when controls are missing remains shared across both controlled environments.",
        "migration_reason": "The chunk describes shared go/no-go behavior for governance and isolated runtime approvals.",
    },
    "KB-DEL-001#chunk-000-ed0ad536a5c8": {
        "inherits_document_scope": True,
        "target_scope_type": "cross_cutting_requirement",
        "primary_solution_id": "服务工单系统集成方案",
        "applicable_solution_ids": ["服务工单系统集成方案", "私有化大模型部署方案"],
        "excluded_solution_ids": [],
        "scope_notes": "Historical delivery constraints remain shared across service integration and private deployment.",
        "migration_reason": "The chunk documents a shared expired delivery backdrop for two solutions.",
    },
    "KB-DEL-001#chunk-001-1946c97670c2": {
        "inherits_document_scope": True,
        "target_scope_type": "cross_cutting_requirement",
        "primary_solution_id": "服务工单系统集成方案",
        "applicable_solution_ids": ["服务工单系统集成方案", "私有化大模型部署方案"],
        "excluded_solution_ids": [],
        "scope_notes": "Current-state delivery boundary remains shared across the same two delivery-sensitive solutions.",
        "migration_reason": "The chunk carries current-state delivery limits shared by integration and deployment work.",
    },
    "KB-INT-001#chunk-000-17c42e00f4ee": {
        "inherits_document_scope": True,
        "target_scope_type": "cross_cutting_requirement",
        "primary_solution_id": "客户身份统一与数据集成方案",
        "applicable_solution_ids": ["客户身份统一与数据集成方案", "客服辅助回复方案"],
        "excluded_solution_ids": [],
        "scope_notes": "The prerequisite integration chunk stays shared across identity unification and assistive reply.",
        "migration_reason": "Chunk content directly links identity integration prerequisites to assistive reply context quality.",
    },
    "KB-INT-001#chunk-001-87ede957932e": {
        "inherits_document_scope": False,
        "target_scope_type": "solution_specific",
        "primary_solution_id": "客户身份统一与数据集成方案",
        "applicable_solution_ids": ["客户身份统一与数据集成方案"],
        "excluded_solution_ids": [],
        "scope_notes": "Validation metrics for identity hit rate and cross-channel consistency are narrowed to the identity-integration solution.",
        "migration_reason": "This chunk is primarily about validating identity integration quality, not a standalone assistive reply capability.",
    },
    "KB-INT-002#chunk-000-37797d7945a6": {
        "inherits_document_scope": True,
        "target_scope_type": "cross_cutting_requirement",
        "primary_solution_id": "服务工单系统集成方案",
        "applicable_solution_ids": ["商品知识库RAG方案", "服务工单系统集成方案"],
        "excluded_solution_ids": [],
        "scope_notes": "The prerequisite integration chunk remains shared across work-order state and product-knowledge retrieval.",
        "migration_reason": "Chunk content couples work-order fields with knowledge-scope filtering.",
    },
    "KB-INT-002#chunk-001-260073642291": {
        "inherits_document_scope": False,
        "target_scope_type": "solution_specific",
        "primary_solution_id": "服务工单系统集成方案",
        "applicable_solution_ids": ["服务工单系统集成方案"],
        "excluded_solution_ids": [],
        "scope_notes": "The validation and fallback chunk is narrowed to service work-order integration.",
        "migration_reason": "Chunk content focuses on field availability, status delay, and fallback behavior in the service workflow.",
    },
    "KB-COM-001#chunk-000-c29de4d33d60": {
        "inherits_document_scope": True,
        "target_scope_type": "global_policy",
        "primary_solution_id": None,
        "applicable_solution_ids": [
            "合规政策RAG检索助手",
            "客户身份统一与数据集成方案",
            "商品知识库RAG方案",
            "客服辅助回复方案",
            "服务工单系统集成方案",
            "私有化大模型部署方案",
        ],
        "excluded_solution_ids": [],
        "scope_notes": "Commercial demo boundary applies globally across all six demo solutions.",
        "migration_reason": "Chunk text states that pricing, discounting, and launch commitments require human approval for the entire demo scope.",
    },
    "KB-COM-001#chunk-001-6e514bb768c3": {
        "inherits_document_scope": True,
        "target_scope_type": "global_policy",
        "primary_solution_id": None,
        "applicable_solution_ids": [
            "合规政策RAG检索助手",
            "客户身份统一与数据集成方案",
            "商品知识库RAG方案",
            "客服辅助回复方案",
            "服务工单系统集成方案",
            "私有化大模型部署方案",
        ],
        "excluded_solution_ids": [],
        "scope_notes": "No-auto-commitment policy applies globally across all six demo solutions.",
        "migration_reason": "Chunk text explicitly says the commercial promise boundary applies to the entire demo solution set.",
    },
    "KB-UNS-001#chunk-000-29c7c8c2317d": {
        "inherits_document_scope": True,
        "target_scope_type": "cross_cutting_requirement",
        "primary_solution_id": "合规政策RAG检索助手",
        "applicable_solution_ids": ["合规政策RAG检索助手", "客服辅助回复方案", "私有化大模型部署方案"],
        "excluded_solution_ids": [],
        "scope_notes": "Unsupported-scenario enumeration remains shared across three bounded solutions.",
        "migration_reason": "Chunk text explicitly enumerates unsupported claims for three different solutions in one shared boundary note.",
    },
    "KB-UNS-001#chunk-001-6221cccec3f8": {
        "inherits_document_scope": True,
        "target_scope_type": "cross_cutting_requirement",
        "primary_solution_id": "合规政策RAG检索助手",
        "applicable_solution_ids": ["合规政策RAG检索助手", "客服辅助回复方案", "私有化大模型部署方案"],
        "excluded_solution_ids": [],
        "scope_notes": "Clarification-only fallback guidance remains shared across the same three bounded solutions.",
        "migration_reason": "Chunk text discusses clarifying governance, approvals, deployment responsibility, and human review across the three bounded scenarios.",
    },
    "KB-READY-001#chunk-000-c25bf83f023f": {
        "inherits_document_scope": True,
        "target_scope_type": "cross_cutting_requirement",
        "primary_solution_id": "商品知识库RAG方案",
        "applicable_solution_ids": ["商品知识库RAG方案", "合规政策RAG检索助手"],
        "excluded_solution_ids": [],
        "scope_notes": "Readiness prerequisites remain shared across product and policy knowledge governance.",
        "migration_reason": "Chunk text explicitly references product knowledge and policy knowledge governance together.",
    },
    "KB-READY-001#chunk-001-3b055dc87afd": {
        "inherits_document_scope": True,
        "target_scope_type": "cross_cutting_requirement",
        "primary_solution_id": "商品知识库RAG方案",
        "applicable_solution_ids": ["商品知识库RAG方案", "合规政策RAG检索助手"],
        "excluded_solution_ids": [],
        "scope_notes": "Remediation guidance remains shared across product and policy knowledge governance readiness.",
        "migration_reason": "Chunk text discusses shared remediation steps for incomplete knowledge-governance readiness.",
    },
    "KB-READY-002#chunk-000-be9fffe3ad6d": {
        "inherits_document_scope": True,
        "target_scope_type": "cross_cutting_requirement",
        "primary_solution_id": "客户身份统一与数据集成方案",
        "applicable_solution_ids": ["客户身份统一与数据集成方案", "服务工单系统集成方案", "私有化大模型部署方案"],
        "excluded_solution_ids": [],
        "scope_notes": "Readiness prerequisites remain shared across identity, service integration, and private deployment.",
        "migration_reason": "Chunk text explicitly names responsibility teams, interfaces, and deployment cadence across three solutions.",
    },
    "KB-READY-002#chunk-001-a9c933dcf327": {
        "inherits_document_scope": True,
        "target_scope_type": "cross_cutting_requirement",
        "primary_solution_id": "客户身份统一与数据集成方案",
        "applicable_solution_ids": ["客户身份统一与数据集成方案", "服务工单系统集成方案", "私有化大模型部署方案"],
        "excluded_solution_ids": [],
        "scope_notes": "Remediation guidance remains shared across identity, service integration, and private deployment readiness.",
        "migration_reason": "Chunk text discusses missing budget, deployment responsibility, and interface readiness across the same three solutions.",
    },
}

CASE_V2_OVERRIDES: dict[str, dict[str, Any]] = {
    "RET-005": {
        "allowed_document_types": ["unsupported_scenario", "solution", "capability"],
        "expected_relevant_document_ids": ["KB-SOL-001"],
        "expected_relevant_chunk_ids": ["KB-SOL-001#chunk-001-5b4fdfa84476", "KB-CAP-001#chunk-001-bcb4fc0bf316"],
        "migration_status": "adjusted_expected_ids_for_boundary_safety",
        "gold_changed": True,
        "boundary_changed": True,
        "migration_reason": "Replaced forbidden-scope unsupported/security expectations with compliance-only solution and capability evidence while preserving the legal-judgment business question.",
    },
    "RET-006": {
        "allowed_document_types": ["unsupported_scenario", "readiness_requirement", "solution"],
        "expected_relevant_document_ids": ["KB-SOL-003", "KB-SOL-004"],
        "expected_relevant_chunk_ids": ["KB-SOL-003#chunk-001-adb6d47feec4", "KB-SOL-004#chunk-001-d15a10f713d4"],
        "migration_status": "rewritten_for_feasibility",
        "gold_changed": True,
        "boundary_changed": True,
        "migration_reason": "Replaced v1 conflicting unsupported/readiness expectations with solution-specific boundary evidence for product knowledge and assistive reply under the same business scenario.",
    },
    "RET-009": {
        "allowed_document_types": ["security_compliance", "capability", "solution"],
        "expected_relevant_document_ids": ["KB-SEC-001", "KB-SOL-001"],
        "expected_relevant_chunk_ids": ["KB-SEC-001#chunk-000-f8c40d662005", "KB-CAP-001#chunk-001-bcb4fc0bf316"],
        "migration_status": "rewritten_for_feasibility",
        "gold_changed": True,
        "boundary_changed": True,
        "migration_reason": "Replaced a mixed-solution capability/document expectation with compliance-safe citation and escalation evidence while preserving the compliance auditability scenario.",
    },
}

SPECIAL_CASE_AUDIT: dict[str, dict[str, Any]] = {
    "RET-001": {
        "result": "natural_resolution_under_v2_scope",
        "details": "Expected items stayed unchanged; v2 method-aware scope keeps compliance evidence separate from forbidden customer-service scope.",
    },
    "RET-002": {
        "result": "natural_resolution_under_v2_scope",
        "details": "Expected identity and playbook evidence remained boundary-safe without changing gold semantics.",
    },
    "RET-005": {
        "result": "gold_adjusted_for_boundary_safety",
        "details": "The forbidden multi-solution expectation was replaced by compliance-safe solution evidence plus a compliance-only capability chunk.",
    },
    "RET-006": {
        "result": "rewritten_for_feasibility",
        "details": "v1 expected items conflicted with forbidden compliance scope; v2 now uses product-knowledge and assistive-reply boundary chunks.",
    },
    "RET-009": {
        "result": "rewritten_for_feasibility",
        "details": "v1 expected items mixed compliance and customer-service scope; v2 keeps only compliance-safe citation and escalation evidence.",
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan, write, or verify Retrieval Benchmark v2 data artifacts.")
    parser.add_argument("--write", action="store_true", help="Build and atomically write tracked Retrieval Benchmark v2 artifacts.")
    parser.add_argument("--check", action="store_true", help="Rebuild and compare tracked Retrieval Benchmark v2 artifacts.")
    args = parser.parse_args()

    if args.write and args.check:
        print("Choose either --write or --check, not both.", file=sys.stderr)
        return 2

    artifacts = build_all_artifacts()
    if args.check:
        return _check_artifacts(artifacts)
    if args.write:
        if artifacts["retrieval_case_feasibility"]["summary"]["infeasible_case_count"] != 0:
            print("Retrieval Benchmark v2 write is blocked because one or more v2 cases are infeasible.", file=sys.stderr)
            return 1
        _write_artifacts(artifacts)
        print(
            json.dumps(
                {
                    "benchmark_version": artifacts["retrieval_benchmark_config"]["benchmark_version"],
                    "document_count": artifacts["retrieval_benchmark_config"]["document_count"],
                    "chunk_count": artifacts["retrieval_benchmark_config"]["chunk_count"],
                    "case_count": artifacts["retrieval_benchmark_config"]["case_count"],
                    "feasible_case_count": artifacts["retrieval_case_feasibility"]["summary"]["feasible_case_count"],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0

    plan_payload = {
        "mode": "plan",
        "document_count": len(artifacts["documents_v2"]),
        "chunk_count": len(artifacts["chunks_v2"]),
        "case_count": len(artifacts["retrieval_cases_v2"]),
        "feasible_case_count": artifacts["retrieval_case_feasibility"]["summary"]["feasible_case_count"],
        "special_case_audit_keys": sorted(SPECIAL_CASE_AUDIT),
        "planned_files": [
            str(V2_SCOPE_MIGRATION_PATH),
            str(V2_DOCUMENTS_PATH),
            str(V2_CHUNKS_PATH),
            str(V2_MANIFEST_PATH),
            str(V2_CASE_MIGRATION_PATH),
            str(V2_CASES_PATH),
            str(V2_FEASIBILITY_PATH),
            str(V2_CONFIG_PATH),
        ],
    }
    print(json.dumps(plan_payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def build_all_artifacts() -> dict[str, Any]:
    v1_hashes_before = _compute_file_hashes(FROZEN_V1_PATHS)
    v1_documents = load_knowledge_documents(V1_DOCUMENTS_PATH)
    v1_chunks = load_knowledge_chunks(V1_CHUNKS_PATH)
    v1_manifest = load_knowledge_manifest(V1_MANIFEST_PATH)
    v1_cases = load_retrieval_evaluation_cases(V1_CASES_PATH)
    demo_scope = load_demo_solution_scope(V1_SCOPE_PATH)

    scope_migration = build_solution_scope_migration_payload(
        documents=v1_documents,
        chunks=v1_chunks,
        source_v1_hashes=v1_hashes_before,
        demo_scope_version=demo_scope.scope_version,
    )
    document_scope_map = {
        record["document_id"]: record_to_scope(record)
        for record in scope_migration["document_scope_migrations"]
    }
    chunk_scope_map = {
        record["chunk_id"]: record_to_scope(record)
        for record in scope_migration["chunk_scope_migrations"]
    }

    documents_v2_models = [
        KnowledgeDocumentV2.from_v1(document, scope=document_scope_map[document.document_id])
        for document in v1_documents
    ]
    chunks_v2_models = [
        KnowledgeChunkV2.from_v1(chunk, scope=chunk_scope_map[chunk.chunk_id])
        for chunk in v1_chunks
    ]
    documents_by_id_v2 = {document.document_id: document for document in documents_v2_models}
    for chunk in chunks_v2_models:
        validate_chunk_scope_against_document_v2(chunk=chunk, document=documents_by_id_v2[chunk.document_id])

    _validate_v1_v2_content_consistency(v1_documents=v1_documents, v1_chunks=v1_chunks, documents_v2=documents_v2_models, chunks_v2=chunks_v2_models)

    documents_v2_payloads = [document.model_dump(mode="json") for document in documents_v2_models]
    chunks_v2_payloads = [chunk.model_dump(mode="json") for chunk in chunks_v2_models]
    documents_v2_text = _serialize_jsonl(documents_v2_payloads)
    chunks_v2_text = _serialize_jsonl(chunks_v2_payloads)
    scope_migration_text = _serialize_json(scope_migration)

    manifest_v2 = {
        "manifest_version": "1.0",
        "contract_version": KB_CONTRACT_VERSION,
        "knowledge_base_version": "kb-demo-v2",
        "document_count": len(documents_v2_payloads),
        "chunk_count": len(chunks_v2_payloads),
        "demo_solution_count": len(demo_scope.selected_solution_ids),
        "source_v1_manifest_hash": v1_hashes_before["manifest_v1"],
        "solution_scope_migration_hash": _sha256_text(scope_migration_text),
        "documents_v2_hash": _sha256_text(documents_v2_text),
        "chunks_v2_hash": _sha256_text(chunks_v2_text),
        "build_tool_version": BUILD_TOOL_VERSION,
        "source_v1_hashes": {
            "documents_v1": v1_hashes_before["documents_v1"],
            "chunks_v1": v1_hashes_before["chunks_v1"],
            "manifest_v1": v1_hashes_before["manifest_v1"],
            "demo_scope_v1": v1_hashes_before["demo_scope_v1"],
        },
    }

    case_migration = build_retrieval_case_migration_payload(
        cases=v1_cases,
        source_v1_hashes=v1_hashes_before,
    )
    case_migration_text = _serialize_json(case_migration)
    retrieval_cases_v2_models = build_retrieval_cases_v2(v1_cases)
    retrieval_cases_v2_payloads = [case.model_dump(mode="json") for case in retrieval_cases_v2_models]
    retrieval_cases_v2_text = _serialize_jsonl(retrieval_cases_v2_payloads)

    feasibility_payload = build_feasibility_payload(
        cases=retrieval_cases_v2_models,
        documents=documents_v2_models,
        chunks=chunks_v2_models,
    )
    feasibility_text = _serialize_json(feasibility_payload)

    benchmark_config = {
        "benchmark_version": BENCHMARK_VERSION,
        "retrieval_contract_version": RETRIEVAL_CONTRACT_VERSION,
        "failure_taxonomy_version": FAILURE_TAXONOMY_VERSION,
        "knowledge_contract_version": KB_CONTRACT_VERSION,
        "boundary_contract_version": BOUNDARY_CONTRACT_VERSION,
        "document_file": str(V2_DOCUMENTS_PATH),
        "chunk_file": str(V2_CHUNKS_PATH),
        "manifest_file": str(V2_MANIFEST_PATH),
        "case_file": str(V2_CASES_PATH),
        "feasibility_file": str(V2_FEASIBILITY_PATH),
        "dataset_hashes": {
            "documents_v2": _sha256_text(documents_v2_text),
            "chunks_v2": _sha256_text(chunks_v2_text),
            "manifest_v2": _sha256_text(_serialize_json(manifest_v2)),
            "solution_scope_migration_v2": _sha256_text(scope_migration_text),
            "retrieval_case_migration_v2": _sha256_text(case_migration_text),
            "retrieval_cases_v2": _sha256_text(retrieval_cases_v2_text),
            "retrieval_case_feasibility_v2": _sha256_text(feasibility_text),
        },
        "document_count": 20,
        "chunk_count": 40,
        "case_count": 16,
        "demo_solution_count": 6,
        "evaluation_date": EVALUATION_DATE,
        "top_k": TOP_K,
        "metrics": {
            "case_metrics": [
                "recall_at_1",
                "recall_at_3",
                "recall_at_5",
                "precision_at_3",
                "precision_at_5",
                "mean_reciprocal_rank",
                "forbidden_hit_rate",
                "solution_boundary_violation_rate",
            ],
            "feasibility_gate_required": True,
        },
        "blocking_gate": {
            "summary_recall_at_5_equals": 1.0,
            "summary_forbidden_hit_rate_equals": 0.0,
            "summary_solution_boundary_violation_rate_equals": 0.0,
            "summary_request_error_count_equals": 0,
            "all_cases_pass_blocking_gate": True,
        },
        "runtime_gold_isolation_required": True,
        "all_cases_feasible": feasibility_payload["summary"]["infeasible_case_count"] == 0,
        "retriever_algorithms_frozen_for_first_v2_run": True,
        "source_v1_hashes": v1_hashes_before,
    }

    v1_hashes_after = _compute_file_hashes(FROZEN_V1_PATHS)
    if v1_hashes_before != v1_hashes_after:
        raise ValueError("Frozen v1 files changed during v2 build planning, which is not allowed.")

    return {
        "solution_scope_migration": scope_migration,
        "documents_v2": documents_v2_payloads,
        "chunks_v2": chunks_v2_payloads,
        "manifest_v2": manifest_v2,
        "retrieval_case_migration": case_migration,
        "retrieval_cases_v2": retrieval_cases_v2_payloads,
        "retrieval_case_feasibility": feasibility_payload,
        "retrieval_benchmark_config": benchmark_config,
        "v1_hashes": v1_hashes_before,
    }


def build_solution_scope_migration_payload(
    *,
    documents: list[KnowledgeDocument],
    chunks: list[KnowledgeChunk],
    source_v1_hashes: dict[str, str],
    demo_scope_version: str,
) -> dict[str, Any]:
    document_records: list[dict[str, Any]] = []
    chunk_records: list[dict[str, Any]] = []
    document_map = {document.document_id: document for document in documents}
    chunk_map = {chunk.chunk_id: chunk for chunk in chunks}

    for document in documents:
        record = _build_document_scope_record(document)
        document_records.append(record)

    for chunk in chunks:
        record = _build_chunk_scope_record(chunk, document_map[chunk.document_id])
        chunk_records.append(record)
        chunk_scope = record_to_scope(record)
        document_scope = record_to_scope(next(item for item in document_records if item["document_id"] == chunk.document_id))
        if not set(chunk_scope.applicable_solution_ids).issubset(set(document_scope.applicable_solution_ids)):
            raise ValueError(f"Chunk migration would expand beyond its document scope: {chunk.chunk_id}")

    inherited_scope_chunk_count = sum(1 for record in chunk_records if record["inherits_document_scope"])
    narrowed_scope_chunk_count = len(chunk_records) - inherited_scope_chunk_count
    stats = {
        "document_count": len(document_records),
        "chunk_count": len(chunk_records),
        "inherited_scope_chunk_count": inherited_scope_chunk_count,
        "narrowed_scope_chunk_count": narrowed_scope_chunk_count,
        "solution_specific_chunk_count": sum(1 for record in chunk_records if record["target_scope_type"] == "solution_specific"),
        "multi_solution_chunk_count": sum(1 for record in chunk_records if record["target_scope_type"] == "multi_solution"),
        "global_policy_chunk_count": sum(1 for record in chunk_records if record["target_scope_type"] == "global_policy"),
        "cross_cutting_chunk_count": sum(1 for record in chunk_records if record["target_scope_type"] == "cross_cutting_requirement"),
        "multi_solution_document_count": sum(
            1
            for record in document_records
            if len(record["source_v1_solution_ids"]) > 1
        ),
    }

    return {
        "migration_version": "1.0",
        "contract_version": KB_CONTRACT_VERSION,
        "demo_solution_scope_version": demo_scope_version,
        "source_v1_hashes": {
            "documents_v1": source_v1_hashes["documents_v1"],
            "chunks_v1": source_v1_hashes["chunks_v1"],
            "manifest_v1": source_v1_hashes["manifest_v1"],
            "demo_scope_v1": source_v1_hashes["demo_scope_v1"],
        },
        "document_scope_migrations": document_records,
        "chunk_scope_migrations": chunk_records,
        "stats": stats,
    }


def _build_document_scope_record(document: KnowledgeDocument) -> dict[str, Any]:
    if len(document.solution_ids) == 1:
        primary_solution_id = document.solution_ids[0]
        return {
            "document_id": document.document_id,
            "source_v1_solution_ids": list(document.solution_ids),
            "target_scope_type": "solution_specific",
            "primary_solution_id": primary_solution_id,
            "applicable_solution_ids": [primary_solution_id],
            "excluded_solution_ids": [],
            "scope_notes": "Single-solution v1 document remains solution_specific in v2.",
            "migration_reason": "Single-solution v1 documents keep their exact business applicability in v2.",
            "decision_source": "Deterministic single-solution migration rule from D4B.",
        }
    override = DOCUMENT_SCOPE_OVERRIDES[document.document_id]
    return {
        "document_id": document.document_id,
        "source_v1_solution_ids": list(document.solution_ids),
        **override,
    }


def _build_chunk_scope_record(chunk: KnowledgeChunk, document: KnowledgeDocument) -> dict[str, Any]:
    if chunk.chunk_id in CHUNK_SCOPE_OVERRIDES:
        record = {
            "chunk_id": chunk.chunk_id,
            "document_id": chunk.document_id,
            **CHUNK_SCOPE_OVERRIDES[chunk.chunk_id],
        }
        return record
    document_record = _build_document_scope_record(document)
    return {
        "chunk_id": chunk.chunk_id,
        "document_id": chunk.document_id,
        "inherits_document_scope": True,
        "target_scope_type": document_record["target_scope_type"],
        "primary_solution_id": document_record["primary_solution_id"],
        "applicable_solution_ids": list(document_record["applicable_solution_ids"]),
        "excluded_solution_ids": list(document_record["excluded_solution_ids"]),
        "scope_notes": "Chunk inherits single-solution document scope without widening.",
        "migration_reason": "Single-solution document chunks preserve the exact v1 business applicability in v2.",
    }


def build_retrieval_case_migration_payload(
    cases: list[RetrievalEvaluationCase],
    *,
    source_v1_hashes: dict[str, str],
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for index, case in enumerate(cases, start=1):
        override = CASE_V2_OVERRIDES.get(case.retrieval_case_id, {})
        records.append(
            {
                "source_retrieval_case_id": case.retrieval_case_id,
                "source_case_id": case.source_case_id,
                "target_case_id": f"RET2-{index:03d}",
                "migration_status": override.get("migration_status", "unchanged_with_runtime_gold_split"),
                "query_changed": False,
                "runtime_context_changed": True,
                "gold_changed": bool(override.get("gold_changed", False)),
                "boundary_changed": bool(override.get("boundary_changed", False)),
                "minimum_relevant_hits_changed": False,
                "migration_reason": override.get(
                    "migration_reason",
                    "Query and business semantics stay the same; runtime-visible filters are separated from evaluation gold in v2.",
                ),
                "source_expected_ids": {
                    "documents": list(case.expected_relevant_document_ids),
                    "chunks": list(case.expected_relevant_chunk_ids),
                },
                "target_expected_ids": {
                    "documents": list(override.get("expected_relevant_document_ids", case.expected_relevant_document_ids)),
                    "chunks": list(override.get("expected_relevant_chunk_ids", case.expected_relevant_chunk_ids)),
                },
                "source_forbidden_ids": {
                    "documents": list(case.forbidden_document_ids),
                    "solutions": list(case.forbidden_solution_ids),
                },
                "target_forbidden_ids": {
                    "documents": list(case.forbidden_document_ids),
                    "solutions": list(case.forbidden_solution_ids),
                },
            }
        )
    return {
        "migration_version": "1.0",
        "retrieval_contract_version": RETRIEVAL_CONTRACT_VERSION,
        "source_v1_hashes": {
            "retrieval_cases_v1": source_v1_hashes["retrieval_cases_v1"],
            "failure_analysis_v1": source_v1_hashes["failure_analysis_v1"],
            "migration_plan_v1": source_v1_hashes["migration_plan_v1"],
        },
        "case_migrations": records,
        "special_case_audit": SPECIAL_CASE_AUDIT,
    }


def build_retrieval_cases_v2(cases: list[RetrievalEvaluationCase]) -> list[RetrievalEvaluationCaseV2]:
    result: list[RetrievalEvaluationCaseV2] = []
    for index, case in enumerate(cases, start=1):
        override = CASE_V2_OVERRIDES.get(case.retrieval_case_id, {})
        result.append(
            RetrievalEvaluationCaseV2(
                retrieval_case_id=f"RET2-{index:03d}",
                source_case_id=case.source_case_id,
                query_type=case.query_type,
                query=case.query,
                runtime_context=RetrievalRuntimeContextV2(
                    operational_filters={},
                    operational_solution_scope=list(case.required_solution_ids),
                    allowed_document_types=list(override.get("allowed_document_types", case.filters.get("document_types", []))),
                    industries=list(case.filters.get("industries", [])),
                    tags=list(case.filters.get("tags", [])),
                    effective_on=date.fromisoformat(EVALUATION_DATE),
                ),
                evaluation_gold=RetrievalEvaluationGoldV2(
                    expected_relevant_document_ids=list(override.get("expected_relevant_document_ids", case.expected_relevant_document_ids)),
                    expected_relevant_chunk_ids=list(override.get("expected_relevant_chunk_ids", case.expected_relevant_chunk_ids)),
                    forbidden_document_ids=list(case.forbidden_document_ids),
                    forbidden_solution_ids=list(case.forbidden_solution_ids),
                    minimum_relevant_hits=case.minimum_relevant_hits,
                ),
                tags=list(case.tags),
                notes=list(case.notes),
            )
        )
    return result


def build_feasibility_payload(
    *,
    cases: list[RetrievalEvaluationCaseV2],
    documents: list[KnowledgeDocumentV2],
    chunks: list[KnowledgeChunkV2],
) -> dict[str, Any]:
    per_case: list[dict[str, Any]] = []
    feasible_case_ids: list[str] = []
    infeasible_case_ids: list[str] = []
    for case in cases:
        result = validate_retrieval_case_feasibility_v2(
            case=case,
            documents=documents,
            chunks=chunks,
            evaluation_date=date.fromisoformat(EVALUATION_DATE),
        )
        record = {
            "case_id": case.retrieval_case_id,
            "source_case_id": case.source_case_id,
            "feasible": result.feasible,
            "reasons": list(result.reasons),
            "safe_expected_item_count": result.safe_expected_item_count,
            "filtered_expected_item_count": result.filtered_expected_item_count,
            "boundary_safe_expected_item_count": result.boundary_safe_expected_item_count,
            "expected_document_count": len(case.evaluation_gold.expected_relevant_document_ids),
            "expected_chunk_count": len(case.evaluation_gold.expected_relevant_chunk_ids),
            "operational_scope_count": len(case.runtime_context.operational_solution_scope),
        }
        per_case.append(record)
        if result.feasible:
            feasible_case_ids.append(case.retrieval_case_id)
        else:
            infeasible_case_ids.append(case.retrieval_case_id)
    return {
        "feasibility_version": "1.0",
        "retrieval_contract_version": RETRIEVAL_CONTRACT_VERSION,
        "evaluation_date": EVALUATION_DATE,
        "cases": per_case,
        "summary": {
            "case_count": len(cases),
            "feasible_case_count": len(feasible_case_ids),
            "infeasible_case_count": len(infeasible_case_ids),
            "feasible_case_ids": feasible_case_ids,
            "infeasible_case_ids": infeasible_case_ids,
        },
    }


def _validate_v1_v2_content_consistency(
    *,
    v1_documents: list[KnowledgeDocument],
    v1_chunks: list[KnowledgeChunk],
    documents_v2: list[KnowledgeDocumentV2],
    chunks_v2: list[KnowledgeChunkV2],
) -> None:
    documents_v2_by_id = {document.document_id: document for document in documents_v2}
    chunks_v2_by_id = {chunk.chunk_id: chunk for chunk in chunks_v2}
    for v1_document in v1_documents:
        v2_document = documents_v2_by_id[v1_document.document_id]
        if document_content_projection_v1(v1_document) != document_content_projection_v1(v2_document):
            raise ValueError(f"V1/V2 document payload mismatch for {v1_document.document_id}")
    for v1_chunk in v1_chunks:
        v2_chunk = chunks_v2_by_id[v1_chunk.chunk_id]
        if chunk_content_projection_v1(v1_chunk) != chunk_content_projection_v1(v2_chunk):
            raise ValueError(f"V1/V2 chunk payload mismatch for {v1_chunk.chunk_id}")


def _check_artifacts(artifacts: dict[str, Any]) -> int:
    tracked_payloads = {
        str(V2_SCOPE_MIGRATION_PATH): load_json_record(V2_SCOPE_MIGRATION_PATH),
        str(V2_DOCUMENTS_PATH): load_jsonl_records(V2_DOCUMENTS_PATH),
        str(V2_CHUNKS_PATH): load_jsonl_records(V2_CHUNKS_PATH),
        str(V2_MANIFEST_PATH): load_json_record(V2_MANIFEST_PATH),
        str(V2_CASE_MIGRATION_PATH): load_json_record(V2_CASE_MIGRATION_PATH),
        str(V2_CASES_PATH): load_jsonl_records(V2_CASES_PATH),
        str(V2_FEASIBILITY_PATH): load_json_record(V2_FEASIBILITY_PATH),
        str(V2_CONFIG_PATH): load_json_record(V2_CONFIG_PATH),
    }
    current_payloads = {
        str(V2_SCOPE_MIGRATION_PATH): artifacts["solution_scope_migration"],
        str(V2_DOCUMENTS_PATH): artifacts["documents_v2"],
        str(V2_CHUNKS_PATH): artifacts["chunks_v2"],
        str(V2_MANIFEST_PATH): artifacts["manifest_v2"],
        str(V2_CASE_MIGRATION_PATH): artifacts["retrieval_case_migration"],
        str(V2_CASES_PATH): artifacts["retrieval_cases_v2"],
        str(V2_FEASIBILITY_PATH): artifacts["retrieval_case_feasibility"],
        str(V2_CONFIG_PATH): artifacts["retrieval_benchmark_config"],
    }
    differences: list[str] = []
    for path, tracked in tracked_payloads.items():
        current = current_payloads[path]
        for difference in diff_json_objects(tracked, current):
            differences.append(f"{path}:{difference}")
    if differences:
        for difference in differences:
            print(difference, file=sys.stderr)
        return 1
    print("Retrieval Benchmark v2 artifacts are up to date.")
    return 0


def _write_artifacts(artifacts: dict[str, Any]) -> None:
    items = [
        (V2_SCOPE_MIGRATION_PATH, _serialize_json(artifacts["solution_scope_migration"])),
        (V2_DOCUMENTS_PATH, _serialize_jsonl(artifacts["documents_v2"])),
        (V2_CHUNKS_PATH, _serialize_jsonl(artifacts["chunks_v2"])),
        (V2_MANIFEST_PATH, _serialize_json(artifacts["manifest_v2"])),
        (V2_CASE_MIGRATION_PATH, _serialize_json(artifacts["retrieval_case_migration"])),
        (V2_CASES_PATH, _serialize_jsonl(artifacts["retrieval_cases_v2"])),
        (V2_FEASIBILITY_PATH, _serialize_json(artifacts["retrieval_case_feasibility"])),
        (V2_CONFIG_PATH, _serialize_json(artifacts["retrieval_benchmark_config"])),
    ]
    write_many_atomic([(str(path), content) for path, content in items])


def record_to_scope(record: dict[str, Any]) -> SolutionScopeV2:
    return SolutionScopeV2(
        primary_solution_id=record["primary_solution_id"],
        applicable_solution_ids=list(record["applicable_solution_ids"]),
        excluded_solution_ids=list(record["excluded_solution_ids"]),
        scope_type=record["target_scope_type"],
        scope_notes=record["scope_notes"],
    )


def _compute_file_hashes(paths: dict[str, Path]) -> dict[str, str]:
    return {label: hashlib.sha256(path.read_bytes()).hexdigest() for label, path in paths.items()}


def _serialize_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def _serialize_jsonl(records: list[dict[str, Any]]) -> str:
    return "\n".join(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) for record in records) + "\n"


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
