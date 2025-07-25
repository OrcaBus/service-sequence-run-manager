# generated by datamodel-codegen:
#   filename:  SequenceRunStateChange.schema.json
#   timestamp: 2025-07-09T16:34:47+00:00

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional, Union

from pydantic import BaseModel, Field


class SequenceRunStateChange(BaseModel):
    id: str
    instrumentRunId: str
    runVolumeName: str
    runFolderPath: str
    runDataUri: str
    sampleSheetName: str
    startTime: datetime
    endTime: Optional[Union[datetime, Any]] = None
    status: str


class AWSEvent(BaseModel):
    id: Optional[str] = None
    region: Optional[str] = None
    resources: Optional[List[str]] = None
    source: str
    time: Optional[datetime] = None
    version: Optional[str] = None
    account: Optional[str] = None
    detail_type: str = Field(..., alias='detail_type')
    detail: SequenceRunStateChange
