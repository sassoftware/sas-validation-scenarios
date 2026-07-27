/*************************************/
/*********** SETUP SESSION ***********/
/*************************************/

%put ===== SYSPARM=[&sysparm] =====;

%let cadence=%scan(&sysparm,1,#);
%let loopcount=%scan(&sysparm,2,#);


%put ===== CADENCE=[&cadence] =====;
%put ===== LOOPCOUNT=[&loopcount] =====;

/* Load the macro definition */
%include "/riskcirruscore/icm/code_libraries/icm/release-icm-&cadence./spre/sas/ucmacros/icm_rest_attachment_request.sas";


/* Setup parameters */
%let solution     = icm;
%let folder_path  = /Products/SAS Insurance Capital Management/&cadence./spre/sas/batch;
%let batch_file_type = filesrvc;
%let log_options  = nomprint nomlogic nosymbolgen;



/* Setup Cirrus Core code libraries */
%let core_root_path = /riskcirruscore/core/code_libraries/release-core-&cadence.;
%let icm_root_path  = /riskcirruscore/icm/code_libraries/icm/release-icm-&cadence.;

option insert = (
    SASAUTOS = (
        "&core_root_path./sas/ucmacros"
        "&icm_root_path./sas/ucmacros"
        "&icm_root_path./s2/spre/ucmacros"
        "&icm_root_path./s2/scripts"
        "&icm_root_path./scripts"
    )
);

filename LUAPATH "&core_root_path./lua";

/* Macro to run iterations */
%macro run_iterations;
    %do myiteration = 1 %to &loopcount;

        %let batch_file_name = icm_s2_&cadence..xlsx;
        %put NOTE: Using Excel file &batch_file_name;

        filename myfile filesrvc folderpath="&folder_path." filename="&batch_file_name.";
        proc import datafile=myfile dbms=xlsx out=work.cycles replace;
            sheet="cycles";
        run;

        %if not %sysfunc(exist(work.cycles)) %then %do;
            %put ERROR: Import failed. Check sheet name in &batch_file_name.;
            %abort cancel;
        %end;

        /* Build batch parameters */
        data batch_parameters;
            length name $100 value $100;
            name="solution";   value=upcase("&solution."); output;
            name="name"; value="icm_s2_&cadence."; output;
            name="folderPath"; value="&folder_path.";      output;
            name="filename";   value="&batch_file_name.";  output;
            name="fileType";   value="&batch_file_type.";  output;
            name="jobTimeoutMin"; value="180";             output;
        run;

        %core_rest_run_batch_job(
            ds_in_batch_parameters = work.batch_parameters,
            wait_flg = Y,
            pollInterval = 10,
            maxWait = 7200,
            timeoutSeverity = ERROR,
            outbatchJobId = batch_job_id,
            outbatchJobStatus = batch_job_status,
            debug = false,
            logOptions = &log_options.
        );

        %put == Batch jobID: &batch_job_id ==;
        %put == Batch jobStatus: &batch_job_status ==;
        
        /************** GET NEW JOB LOG **************/
	      %core_rest_get_batch_job_log(  job_id = &batch_job_id.
                             , printLog = N
                             , logtype = log
                             , debug = false
                             , logOptions = &log_options.
                             );

       	/************** GET NEW JOB INFO **************/
	      %core_rest_get_batch_job(  server = riskCirrusCore
                               , authMethod = bearer
                               , solution = %upcase(&solution.)
                               , start = 0
                               , limit = 100
                               , logSeverity = WARNING
                               , outds_batch_job_info = work.batch_job_info
                               , debug = false
                               , restartLUA = Y
                               , clearCache = Y
                               );


        %put NOTE: Iteration &myiteration completed;
    %end;
%mend;

%run_iterations;