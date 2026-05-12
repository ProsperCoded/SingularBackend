"""
Dummy endpoints to expose all Pydantic schemas on Swagger UI.
These are not meant for production use.
"""

from fastapi import APIRouter
from schemas.schemas import (
    GenerateVendorIdResponse,
    CheckVendorIdResponse,
    ConfirmVendorIdResponse,
    ConfirmVendorId,
    BatchItemResponse,
    BrandBatchesResponse,
    ScanStats,
    ScanResultResponse,
    VendorDashboardResponse,
    VendorTrustInfo,
    ProductDetails,
    VendorPerformance,
    BrandAnalyticsResponse,
)

router = APIRouter(prefix="/schemas", tags=["Schema Preview"])


@router.get(
    "/vendor",
    response_model=VendorDashboardResponse,
    summary="VendorDashboardResponse schema",
    description="Dummy endpoint — shows the VendorDashboardResponse schema.",
)
async def preview_vendor_dashboard():
    ...


@router.get(
    "/vendor-trust",
    response_model=VendorTrustInfo,
    summary="VendorTrustInfo schema",
    description="Dummy endpoint — shows the VendorTrustInfo schema.",
)
async def preview_vendor_trust():
    ...


@router.get(
    "/scan-result",
    response_model=ScanResultResponse,
    summary="ScanResultResponse schema",
    description="Dummy endpoint — shows the ScanResultResponse schema.",
)
async def preview_scan_result():
    ...


@router.get(
    "/scan-stats",
    response_model=ScanStats,
    summary="ScanStats schema",
    description="Dummy endpoint — shows the ScanStats schema.",
)
async def preview_scan_stats():
    ...


@router.get(
    "/product-details",
    response_model=ProductDetails,
    summary="ProductDetails schema",
    description="Dummy endpoint — shows the ProductDetails schema.",
)
async def preview_product_details():
    ...


@router.get(
    "/batch-item",
    response_model=BatchItemResponse,
    summary="BatchItemResponse schema",
    description="Dummy endpoint — shows the BatchItemResponse schema.",
)
async def preview_batch_item():
    ...


@router.get(
    "/brand-batches",
    response_model=BrandBatchesResponse,
    summary="BrandBatchesResponse schema",
    description="Dummy endpoint — shows the BrandBatchesResponse schema.",
)
async def preview_brand_batches():
    ...


@router.get(
    "/brand-analytics",
    response_model=BrandAnalyticsResponse,
    summary="BrandAnalyticsResponse schema",
    description="Dummy endpoint — shows the BrandAnalyticsResponse schema.",
)
async def preview_brand_analytics():
    ...


@router.post(
    "/confirm-vendor-id",
    response_model=ConfirmVendorIdResponse,
    summary="ConfirmVendorId request & response schemas",
    description="Dummy endpoint — shows ConfirmVendorId (request body) and ConfirmVendorIdResponse.",
)
async def preview_confirm_vendor_id(body: ConfirmVendorId):
    ...


@router.get(
    "/generate-vendor-id",
    response_model=GenerateVendorIdResponse,
    summary="GenerateVendorIdResponse schema",
    description="Dummy endpoint — shows the GenerateVendorIdResponse schema.",
)
async def preview_generate_vendor_id():
    ...


@router.get(
    "/check-vendor-id",
    response_model=CheckVendorIdResponse,
    summary="CheckVendorIdResponse schema",
    description="Dummy endpoint — shows the CheckVendorIdResponse schema.",
)
async def preview_check_vendor_id():
    ...


@router.get(
    "/vendor-performance",
    response_model=VendorPerformance,
    summary="VendorPerformance schema",
    description="Dummy endpoint — shows the VendorPerformance schema.",
)
async def preview_vendor_performance():
    ...
