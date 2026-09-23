/* =====================================================================
   Step 3: Add more fund details to FundMaster.
   AMFI lists every fund in several versions (Direct/Regular plan,
   Growth/IDCW option) that share the same name, so we store them too.
   Run    : sqlcmd -S NILU -E -i sql\02_fundmaster_add_details.sql
   Safe to run again: each column is only added if it is missing.
   ===================================================================== */

USE MFPortfolioDB;
GO

-- PLAN and OPTION are reserved words in SQL Server, so the columns are PlanType / OptionType.
IF COL_LENGTH('dbo.FundMaster', 'PlanType') IS NULL
    ALTER TABLE dbo.FundMaster ADD PlanType NVARCHAR(50) NULL;      -- "Direct Plan" / "Regular Plan"

IF COL_LENGTH('dbo.FundMaster', 'OptionType') IS NULL
    ALTER TABLE dbo.FundMaster ADD OptionType NVARCHAR(50) NULL;    -- "Growth Option" / "IDCW Option"

IF COL_LENGTH('dbo.FundMaster', 'SchemeType') IS NULL
    ALTER TABLE dbo.FundMaster ADD SchemeType NVARCHAR(50) NULL;    -- "Open Ended Schemes" etc.

IF COL_LENGTH('dbo.FundMaster', 'ISIN') IS NULL
    ALTER TABLE dbo.FundMaster ADD ISIN VARCHAR(20) NULL;           -- unique ID used on your account statements
GO

PRINT 'Step 3 done: FundMaster now has PlanType, OptionType, SchemeType, ISIN.';
GO
