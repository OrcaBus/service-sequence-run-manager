# generated by datamodel-codegen:
#   filename:  SequenceRunSampleSheetChange.schema.json
#   timestamp: 2025-07-09T16:34:48+00:00

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class Comment(BaseModel):
    comment: str
    created_by: str
    created_at: Optional[datetime] = None


class SequenceRunSampleSheetChange(BaseModel):
    instrumentRunId: str
    sequenceRunId: Optional[str] = None
    timeStamp: str
    sampleSheetName: str
    samplesheetBase64gz: Optional[str] = None
    comment: Optional[Comment] = None


class AWSEvent(BaseModel):
    id: Optional[str] = None
    region: Optional[str] = None
    resources: Optional[List[str]] = None
    source: str
    time: Optional[datetime] = None
    version: Optional[str] = None
    account: Optional[str] = None
    detail_type: str = Field(..., alias='detail_type')
    detail: SequenceRunSampleSheetChange
