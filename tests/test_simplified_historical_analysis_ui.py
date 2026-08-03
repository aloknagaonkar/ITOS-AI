from datetime import date
from itos_platform.historical_analysis_orchestrator import DatePipelineStatus,HistoricalPipelineProgress
from ui.historical_analytics_workspace import PipelineProgressPresenter,pipeline_progress_view,pipeline_stage_rows

def test_progress_view_model_renders_final_results_without_runtime_objects():
 progress=HistoricalPipelineProgress("run","COMPLETE","COMPLETE","COMPLETE",100,100,None,None,"Results ready",1,
  date_statuses=(DatePipelineStatus(date(2026,7,1),underlying="Downloaded",options="Options Unavailable",
   intelligence="Intelligence Complete",outcomes="Outcomes Complete",index="Indexed",final="Candle-only"),))
 view=pipeline_progress_view(progress)
 assert view["percent"]==100 and view["message"]=="Results ready"
 assert view["dates"][0]["Final Status"]=="Candle-only"

def test_progress_contract_clamps_percentages():
 progress=HistoricalPipelineProgress("run","RUNNING","PLAN","RUNNING",120,-1,None,None,"Planning",1)
 assert progress.overall_percent==100 and progress.stage_percent==0

def test_presenter_reuses_one_progress_placeholder():
 class Placeholder:
  calls=0
  def container(self): self.calls+=1; return self
  def __enter__(self): return self
  def __exit__(self,*args): return False
 placeholder=Placeholder(); rendered=[]; presenter=PipelineProgressPresenter(placeholder,rendered.append)
 progress=HistoricalPipelineProgress("run","RUNNING","PLAN","RUNNING",10,50,None,None,"Planning",1)
 presenter(progress); presenter(progress)
 assert placeholder.calls==2 and rendered==[progress,progress]

def test_view_model_preserves_similarity_unavailable_readiness():
 progress=HistoricalPipelineProgress("run","PARTIAL","COMPLETE","PARTIAL",100,100,None,None,"Results ready",1,
  date_statuses=(DatePipelineStatus(date(2026,7,1),underlying="Downloaded",options="Available",
   intelligence="Intelligence Complete",outcomes="Outcomes Complete",index="Index Failed",
   final="Ready — Similarity unavailable"),))
 assert pipeline_progress_view(progress)["dates"][0]["Final Status"]=="Ready — Similarity unavailable"

def test_option_stage_is_terminal_when_intelligence_is_running():
 progress=HistoricalPipelineProgress("run","RUNNING","BUILD_INTELLIGENCE","RUNNING",50,0,date(2026,7,1),None,"Building",1,
  option_total=1,option_complete=1,intelligence_total=1,
  date_statuses=(DatePipelineStatus(date(2026,7,1),underlying="Existing",options="Unavailable"),))
 rows={row["Stage"]:row["Status"] for row in pipeline_stage_rows(progress)}
 assert rows["Historical options"]=="Unavailable"
 assert rows["ITOS intelligence"]=="Running"
