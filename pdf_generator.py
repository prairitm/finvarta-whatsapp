#!/usr/bin/env python3
"""
PDF Generator for Corporate Announcements Report
Creates a focused PDF report using only openai_announcement_summaries.json data
"""

import json
import os
from datetime import datetime
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.platypus import Image
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
import io
from datetime import datetime, timedelta, timezone
import pytz

class CorporateAnnouncementsPDFGenerator:
    def __init__(self, output_filename="Corporate_Announcements_Report.pdf"):
        """
        Initialize the PDF generator
        
        Args:
            output_filename (str): Name of the output PDF file
        """
        self.output_filename = output_filename
        self.styles = getSampleStyleSheet()
        self.setup_custom_styles()
        
    def setup_custom_styles(self):
        """Setup custom paragraph styles for the PDF"""
        # Title style
        self.styles.add(ParagraphStyle(
            name='CustomTitle',
            parent=self.styles['Heading1'],
            fontSize=24,
            spaceAfter=30,
            alignment=TA_CENTER,
            textColor=colors.darkblue
        ))
        
        # Section header style
        self.styles.add(ParagraphStyle(
            name='SectionHeader',
            parent=self.styles['Heading2'],
            fontSize=16,
            spaceAfter=12,
            spaceBefore=20,
            textColor=colors.darkblue,
            borderWidth=1,
            borderColor=colors.darkblue,
            borderPadding=5
        ))
        
        # Subsection style
        self.styles.add(ParagraphStyle(
            name='Subsection',
            parent=self.styles['Heading3'],
            fontSize=14,
            spaceAfter=8,
            spaceBefore=12,
            textColor=colors.darkgreen
        ))
        
        # Data style
        self.styles.add(ParagraphStyle(
            name='DataText',
            parent=self.styles['Normal'],
            fontSize=10,
            spaceAfter=6,
            leftIndent=20
        ))
        
        # Summary style
        self.styles.add(ParagraphStyle(
            name='SummaryText',
            parent=self.styles['Normal'],
            fontSize=11,
            spaceAfter=8,
            leftIndent=15,
            rightIndent=15,
            alignment=TA_LEFT
        ))
        
        # Bold text style
        self.styles.add(ParagraphStyle(
            name='BoldText',
            parent=self.styles['Normal'],
            fontSize=11,
            spaceAfter=8,
            leftIndent=15,
            rightIndent=15,
            alignment=TA_LEFT,
            fontName='Helvetica-Bold'
        ))

    def load_data(self):
        """Load data from openai_announcement_summaries.json or use provided summaries_data"""
        if hasattr(self, 'summaries_data') and self.summaries_data is not None:
            # Use the provided summaries data (for new entries only)
            self.openai_summaries = self.summaries_data
        else:
            # Load all data from file (default behavior)
            self.openai_summaries = self.load_json_file("openai_announcement_summaries.json")
        
    def load_json_file(self, filename):
        """Load JSON data from file"""
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"⚠️  File {filename} not found")
            return []
        except json.JSONDecodeError as e:
            print(f"❌ Error parsing {filename}: {e}")
            return []
    
    def process_bold_text(self, text):
        """Convert **text** to <b>text</b> for bold formatting in PDF"""
        import re
        # Replace **text** with <b>text</b>
        processed_text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
        return processed_text

    def create_title_page(self, story):
        """Create the title page"""
        # Title
        story.append(Paragraph("CORPORATE ANNOUNCEMENTS REPORT", self.styles['CustomTitle']))
        story.append(Spacer(1, 20))
        
        # Subtitle
        story.append(Paragraph("AI-Powered Market Intelligence & Analysis", 
                              self.styles['Heading2']))
        story.append(Spacer(1, 30))
        
        # Report details
        report_date = datetime.now().strftime("%B %d, %Y")
        
        # Get current time in IST
        ist = pytz.timezone('Asia/Kolkata')
        now_ist = datetime.now(ist)
        report_datetime = now_ist.strftime("%B %d, %Y, %I:%M %p IST")
        story.append(Paragraph(f"Generated on: {report_datetime}", self.styles['Normal']))
        story.append(Spacer(1, 20))
        
        # Announcements summary
        if self.openai_summaries:
            announcements_count = len(self.openai_summaries)
            story.append(Paragraph(f"Total Announcements Analyzed: {announcements_count}", self.styles['Heading3']))
            # story.append(Paragraph("Powered by OpenAI GPT-3.5-turbo", self.styles['Heading3']))
        
        story.append(PageBreak())

    def create_summary_section(self, story):
        """Create executive summary section"""
        story.append(Paragraph("EXECUTIVE SUMMARY", self.styles['SectionHeader']))
        
        if not self.openai_summaries:
            story.append(Paragraph("No announcement data available.", self.styles['DataText']))
            return
        
        # Count different document types
        doc_types = {}
        sentiment_counts = {'Positive': 0, 'Negative': 0, 'Neutral': 0}
        companies = set()
        
        for announcement in self.openai_summaries:
            companies.add(announcement.get('company', 'Unknown'))
            
            # Extract document type from summary
            summary = announcement.get('summary', '')
            if 'Document Type:' in summary:
                doc_type = summary.split('Document Type:')[1].split('\n')[0].strip()
                doc_types[doc_type] = doc_types.get(doc_type, 0) + 1
            
            # Extract sentiment
            if 'Sentiment Analysis:' in summary:
                sentiment_text = summary.split('Sentiment Analysis:')[1].strip()
                if 'Positive' in sentiment_text:
                    sentiment_counts['Positive'] += 1
                elif 'Negative' in sentiment_text:
                    sentiment_counts['Negative'] += 1
                else:
                    sentiment_counts['Neutral'] += 1
        
        story.append(Paragraph(f"• <b>Total Announcements:</b> {len(self.openai_summaries)}", self.styles['SummaryText']))
        story.append(Paragraph(f"• <b>Companies Covered:</b> {len(companies)}", self.styles['SummaryText']))
        story.append(Paragraph(f"• <b>Document Types:</b> {len(doc_types)}", self.styles['SummaryText']))
        story.append(Paragraph(f"• <b>Sentiment Distribution:</b> {sentiment_counts['Positive']} Positive, {sentiment_counts['Neutral']} Neutral, {sentiment_counts['Negative']} Negative", 
                              self.styles['SummaryText']))
        
        # Top document types
        # if doc_types:
        #     top_doc_types = sorted(doc_types.items(), key=lambda x: x[1], reverse=True)[:3]
        #     story.append(Paragraph("• Most Common Document Types:", self.styles['SummaryText']))
        #     for doc_type, count in top_doc_types:
        #         story.append(Paragraph(f"  - {doc_type}: {count} announcements", self.styles['DataText']))
        
        # story.append(Spacer(1, 20))

    def create_announcements_overview(self, story):
        """Create announcements overview section"""
        story.append(Paragraph("ANNOUNCEMENTS OVERVIEW", self.styles['SectionHeader']))
        
        if not self.openai_summaries:
            story.append(Paragraph("No announcement data available.", self.styles['DataText']))
            return
        
        # Create overview table
        table_data = [['Company', 'Document Type', 'Sentiment', 'Company URL']]
        
        for announcement in self.openai_summaries:  # Show all announcements
            company = announcement.get('company', 'Unknown')
            company_url = announcement.get('company_url', 'N/A')
            summary = announcement.get('summary', '')
            
            # Extract document type and truncate if too long
            doc_type = 'N/A'
            if 'Document Type:' in summary:
                doc_type = summary.split('Document Type:')[1].split('\n')[0].strip()
                # Truncate document type to fit column
                if len(doc_type) > 40:
                    doc_type = doc_type[:40] + "..."
            
            # Extract sentiment
            sentiment = 'Neutral'
            if 'Sentiment Analysis:' in summary:
                sentiment_text = summary.split('Sentiment Analysis:')[1].strip()
                if 'Positive' in sentiment_text:
                    sentiment = 'Positive'
                elif 'Negative' in sentiment_text:
                    sentiment = 'Negative'
            
            # Truncate URL if too long
            if len(company_url) > 50:
                company_url = company_url[:50] + "..."
            
            table_data.append([
                company,
                doc_type,
                sentiment,
                company_url
            ])
        
        overview_table = Table(table_data, colWidths=[100, 150, 80, 200])
        overview_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),  # Company column centered
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),    # Document Type left aligned
            ('ALIGN', (2, 0), (2, -1), 'CENTER'),  # Sentiment centered
            ('ALIGN', (3, 0), (3, -1), 'LEFT'),    # URL left aligned
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('WRAP', (0, 0), (-1, -1), 'WORD')  # Enable text wrapping
        ]))
        
        story.append(overview_table)
        story.append(Spacer(1, 20))

    def create_detailed_announcements(self, story):
        """Create detailed announcements section"""
        story.append(Paragraph("DETAILED ANNOUNCEMENTS", self.styles['SectionHeader']))
        
        if not self.openai_summaries:
            story.append(Paragraph("No announcement data available.", self.styles['DataText']))
            return
        
        # Show detailed summaries for all announcements
        for i, announcement in enumerate(self.openai_summaries, 1):
            company = announcement.get('company', 'Unknown')
            company_url = announcement.get('company_url', 'N/A')
            summary = announcement.get('summary', 'No summary available')
            
            story.append(Paragraph(f"{i}. {company}", self.styles['Subsection']))
            story.append(Paragraph(f"Company URL: {company_url}", self.styles['DataText']))
            
            # Process summary to handle newlines and bold text
            # Replace \n with <br/> for proper line breaks in PDF
            processed_summary = summary.replace('\n', '<br/>')
            # Convert **text** to <b>text</b> for bold formatting
            processed_summary = self.process_bold_text(processed_summary)
            
            # Show complete summary without truncation
            story.append(Paragraph(processed_summary, self.styles['SummaryText']))
            story.append(Spacer(1, 15))
        
        # All announcements are now shown, no need for additional message

    def create_sentiment_analysis(self, story):
        """Create sentiment analysis section"""
        story.append(Paragraph("SENTIMENT ANALYSIS", self.styles['SectionHeader']))
        
        if not self.openai_summaries:
            story.append(Paragraph("No announcement data available.", self.styles['DataText']))
            return
        
        # Analyze sentiment distribution
        sentiment_counts = {'Positive': 0, 'Negative': 0, 'Neutral': 0}
        positive_companies = []
        negative_companies = []
        
        for announcement in self.openai_summaries:
            company = announcement.get('company', 'Unknown')
            summary = announcement.get('summary', '')
            
            if 'Sentiment Analysis:' in summary:
                sentiment_text = summary.split('Sentiment Analysis:')[1].strip()
                if 'Positive' in sentiment_text:
                    sentiment_counts['Positive'] += 1
                    positive_companies.append(company)
                elif 'Negative' in sentiment_text:
                    sentiment_counts['Negative'] += 1
                    negative_companies.append(company)
                else:
                    sentiment_counts['Neutral'] += 1
        
        # Sentiment distribution
        total = sum(sentiment_counts.values())
        if total > 0:
            story.append(Paragraph("Sentiment Distribution:", self.styles['Subsection']))
            story.append(Paragraph(f"• Positive: {sentiment_counts['Positive']} ({sentiment_counts['Positive']/total*100:.1f}%)", 
                                  self.styles['SummaryText']))
            story.append(Paragraph(f"• Neutral: {sentiment_counts['Neutral']} ({sentiment_counts['Neutral']/total*100:.1f}%)", 
                                  self.styles['SummaryText']))
            story.append(Paragraph(f"• Negative: {sentiment_counts['Negative']} ({sentiment_counts['Negative']/total*100:.1f}%)", 
                                  self.styles['SummaryText']))
        
        # Top positive companies with URLs
        if positive_companies:
            story.append(Paragraph("Companies with Positive Sentiment:", self.styles['Subsection']))
            for company in positive_companies[:5]:
                # Find the announcement for this company to get URL
                company_announcement = next((a for a in self.openai_summaries if a.get('company') == company), None)
                if company_announcement:
                    company_url = company_announcement.get('company_url', 'N/A')
                    story.append(Paragraph(f"• {company} - {company_url}", self.styles['DataText']))
                else:
                    story.append(Paragraph(f"• {company}", self.styles['DataText']))
        
        # Top negative companies with URLs
        if negative_companies:
            story.append(Paragraph("Companies with Negative Sentiment:", self.styles['Subsection']))
            for company in negative_companies[:5]:
                # Find the announcement for this company to get URL
                company_announcement = next((a for a in self.openai_summaries if a.get('company') == company), None)
                if company_announcement:
                    company_url = company_announcement.get('company_url', 'N/A')
                    story.append(Paragraph(f"• {company} - {company_url}", self.styles['DataText']))
                else:
                    story.append(Paragraph(f"• {company}", self.styles['DataText']))

    def generate_pdf(self, output_filename=None):
        """Generate the complete PDF report"""
        print("🔄 Generating Corporate Announcements PDF report...")
        
        # Load data
        self.load_data()
        
        # Use provided filename or default
        filename = output_filename if output_filename else self.output_filename
        
        # Create PDF document
        doc = SimpleDocTemplate(filename, pagesize=A4)
        story = []
        
        # Create all sections
        self.create_title_page(story)
        self.create_summary_section(story)
        story.append(PageBreak())
        
        self.create_sentiment_analysis(story)
        story.append(PageBreak())
        
        self.create_announcements_overview(story)
        story.append(PageBreak())
        
        self.create_detailed_announcements(story)
        story.append(PageBreak())
        
        self.create_sentiment_analysis(story)
        
        # Build PDF
        doc.build(story)
        print(f"✅ PDF report generated successfully: {filename}")

def main():
    """Main function to generate the PDF report"""
    print("📊 Corporate Announcements PDF Generator")
    print("=" * 50)
    
    # Check if required packages are installed
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate
    except ImportError:
        print("❌ Missing required package: reportlab")
        print("Please install: pip install reportlab")
        return
    
    # Generate PDF
    generator = CorporateAnnouncementsPDFGenerator()
    generator.generate_pdf()
    
    print("\n📋 Report Contents:")
    print("• Executive Summary")
    print("• Announcements Overview")
    print("• Detailed Announcements")
    print("• Sentiment Analysis")

if __name__ == "__main__":
    main()