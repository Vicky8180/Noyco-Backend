"""
Response Generator for Accountability Buddy Agent
Generates encouraging, non-judgmental responses for different scenarios
"""

import logging
import random
from typing import Dict, List, Optional, Any
from datetime import datetime, date

from .schema import (
    AccountabilityGoal, DailyCheckIn, ProgressStreak, 
    GoalCategory, ProgressLevel, CheckInResponse,
    UserProfileData, AccountabilityAgentRecord
)

logger = logging.getLogger(__name__)

class AccountabilityResponseGenerator:
    """Generates contextual, encouraging responses for accountability interactions"""
    
    def __init__(self):
        self.encouragement_phrases = {
            "excellent": [
                "Amazing work! You're absolutely crushing it! 🌟",
                "Incredible progress! You should be so proud of yourself! 🎉",
                "You're on fire! This consistency is inspiring! 🔥",
                "Outstanding! You're building such strong habits! 💪"
            ],
            "good": [
                "Great job! You're doing really well! 👏",
                "Nice work! You're building momentum! 🚀",
                "Solid progress! Keep up the good work! ✨",
                "You're doing great! I can see your dedication! 💫"
            ],
            "fair": [
                "Good effort! Every step forward counts! 👍",
                "You're making progress! That's what matters! 🌱",
                "Nice work! You're staying committed! 💚",
                "Keep going! You're building something important! 🏗️"
            ],
            "struggling": [
                "I see you're working hard, even when it's tough! 🤗",
                "Thank you for being honest - that takes courage! 💝",
                "Rough patches are part of the journey - you're not alone! 🫂",
                "You showed up today, and that's what matters! 🌈"
            ],
            "difficult": [
                "It's okay - tomorrow is a fresh start! 🌅",
                "Thank you for checking in, even on a hard day! 💙",
                "Difficult days don't define your journey! 🌊",
                "You're being so brave by continuing to try! 🦋"
            ]
        }
        
        self.streak_celebrations = {
            1: "Great start! Day 1 is always the hardest! 🌟",
            3: "Three days strong! You're building momentum! 🚀",
            7: "One week streak! You're creating a real habit! 🎯",
            14: "Two weeks! You're proving you can do this! 💪",
            21: "21 days! They say it takes 21 days to form a habit - look at you! 🏆",
            30: "One month streak! This is incredible dedication! 👑",
            60: "Two months! You're an inspiration! ⭐",
            90: "90 days! You've transformed your life! 🎉",
            180: "Six months! You're a true champion! 🏅",
            365: "One full year! You're absolutely amazing! 🎊"
        }
        
        self.goal_category_messages = {
            GoalCategory.SOBRIETY: {
                "success": "Every sober day is a victory for your health and future! 💚",
                "struggle": "Recovery isn't linear - you're still on the right path! 🌈",
                "encouragement": "You're choosing your wellbeing every single day! 🌟"
            },
            GoalCategory.MEDITATION: {
                "success": "Your mind is getting stronger with each session! 🧘‍♀️",
                "struggle": "Even a minute of mindfulness makes a difference! ☮️",
                "encouragement": "You're investing in your inner peace! ✨"
            },
            GoalCategory.HEALTH_FITNESS: {
                "success": "Your body is thanking you for this care! 💪",
                "struggle": "Every healthy choice adds up over time! 🌱",
                "encouragement": "You're building a stronger, healthier you! 🏃‍♀️"
            },
            GoalCategory.MENTAL_HEALTH: {
                "success": "Taking care of your mental health is so important! 🧠💚",
                "struggle": "Mental health journeys have ups and downs - that's normal! 🌊",
                "encouragement": "You're prioritizing your wellbeing! 🌸"
            },
            GoalCategory.THERAPY: {
                "success": "Therapy takes courage - you're doing important work! 🌟",
                "struggle": "Healing isn't always linear - keep going! 🌈",
                "encouragement": "You're investing in your growth and healing! 🌱"
            }
        }
        
        self.missed_day_responses = [
            "It's okay! Tomorrow is a fresh start! 🌅",
            "One missed day doesn't erase your progress! 💪",
            "You're human - let's get back on track tomorrow! 🤗",
            "This is just a small bump in your journey! 🛤️",
            "Thank you for being honest - that shows real strength! 💝",
            "Every day is a new chance to succeed! 🌟"
        ]
        
        self.check_in_questions = {
            "morning": [
                "Good morning! How are you feeling about your goals today?",
                "Morning check-in time! What's your energy like for today's goals?",
                "Rise and shine! Ready to tackle your goals today?",
                "Good morning, champion! How are we doing with your goals?"
            ],
            "evening": [
                "Evening reflection time! How did today go with your goals?",
                "End of day check-in! Let's see how you did today!",
                "Time to reflect! How did your goals go today?",
                "Evening check-in! How are you feeling about today's progress?"
            ]
        }
        
    def generate_checkin_greeting(self, user_name: str, checkin_type: str, goals: List[AccountabilityGoal], 
                                user_profile: Optional[UserProfileData] = None) -> str:
        """Generate a personalized greeting for check-in"""
        try:
            greeting_templates = self.check_in_questions.get(checkin_type, self.check_in_questions["morning"])
            base_greeting = random.choice(greeting_templates)
            
            # Personalize with user name
            if user_name and user_name.lower() != "unknown":
                base_greeting = base_greeting.replace("champion", user_name)
            
            # Adapt tone based on user profile
            if user_profile and user_profile.preferences:
                tone = user_profile.preferences.get('tone', 'friendly')
                if tone == 'professional':
                    base_greeting = base_greeting.replace('!', '.').replace('Ready to tackle', 'Let\'s review')
                elif tone == 'casual':
                    base_greeting = base_greeting.replace('Good morning', 'Hey there').replace('How are we doing', 'How\'s it going')
                    
            # Consider personality traits
            if user_profile and user_profile.personality_traits:
                if 'introvert' in user_profile.personality_traits:
                    base_greeting = base_greeting.replace('!', '.').replace('Rise and shine', 'Good morning')
                if 'optimistic' in user_profile.personality_traits:
                    base_greeting += " I know you've got this! ✨"
                    
            if len(goals) == 1:
                goal_text = f"Let's check in on your '{goals[0].title}' goal!"
            elif len(goals) > 1:
                goal_text = f"Let's check in on your {len(goals)} goals!"
            else:
                goal_text = "Let's see how you're doing!"
                
            return f"{base_greeting} {goal_text}"
            
        except Exception as e:
            logger.error(f"❌ Error generating check-in greeting: {e}")
            return "Hi! Ready for your daily check-in?"
            
    def generate_response_to_checkin(self, checkin: DailyCheckIn, goal: AccountabilityGoal, 
                                   streak: Optional[ProgressStreak] = None,
                                   user_profile: Optional[UserProfileData] = None,
                                   agent_record: Optional[AccountabilityAgentRecord] = None) -> str:
        """Generate encouraging response to a completed check-in"""
        try:
            responses = []
            
            # Overall performance response with personalization
            if checkin.progress_level:
                level_responses = self.encouragement_phrases.get(
                    checkin.progress_level.value, 
                    self.encouragement_phrases["fair"]
                )
                base_response = random.choice(level_responses)
                
                # Personalize based on user profile
                if user_profile:
                    base_response = self._personalize_response(base_response, user_profile, agent_record)
                    
                responses.append(base_response)
                
            # Category-specific encouragement
            category_messages = self.goal_category_messages.get(goal.category)
            if category_messages:
                if checkin.overall_score and checkin.overall_score >= 7:
                    responses.append(category_messages["success"])
                elif checkin.overall_score and checkin.overall_score < 5:
                    responses.append(category_messages["struggle"])
                else:
                    responses.append(category_messages["encouragement"])
                    
            # Streak celebration
            if streak and streak.current_streak > 0:
                streak_message = self._get_streak_message(streak.current_streak)
                if streak_message:
                    responses.append(streak_message)
                    
            # Specific response to individual metrics
            metric_responses = self._generate_metric_responses(checkin.responses, goal)
            responses.extend(metric_responses)
            
            # Combine responses
            if responses:
                return " ".join(responses)
            else:
                return "Thanks for checking in! Keep up the great work! 🌟"
                
        except Exception as e:
            logger.error(f"❌ Error generating check-in response: {e}")
            return "Thanks for checking in! You're doing great! 💪"
            
    def generate_missed_day_response(self, goal: AccountabilityGoal, days_missed: int = 1) -> str:
        """Generate non-judgmental response for missed days"""
        try:
            base_response = random.choice(self.missed_day_responses)
            
            # Add context based on goal category
            category_messages = self.goal_category_messages.get(goal.category)
            if category_messages and "struggle" in category_messages:
                base_response += f" {category_messages['struggle']}"
                
            # Add encouragement based on days missed
            if days_missed == 1:
                encouragement = "One day doesn't define your journey!"
            elif days_missed <= 3:
                encouragement = "A few missed days is totally normal - let's restart!"
            else:
                encouragement = "It's never too late to begin again - you've got this!"
                
            return f"{base_response} {encouragement}"
            
        except Exception as e:
            logger.error(f"❌ Error generating missed day response: {e}")
            return "It's okay! Tomorrow is a fresh start! 🌅"
            
    def generate_goal_creation_response(self, goal: AccountabilityGoal) -> str:
        """Generate response when a new goal is created"""
        try:
            responses = [
                f"Awesome! I'm excited to help you with '{goal.title}'! 🎯",
                f"Great choice setting up '{goal.title}' - I'll be here to support you! 💪",
                f"I love that you're committing to '{goal.title}'! Let's make it happen! 🌟"
            ]
            
            base_response = random.choice(responses)
            
            # Add category-specific encouragement
            category_messages = self.goal_category_messages.get(goal.category)
            if category_messages and "encouragement" in category_messages:
                base_response += f" {category_messages['encouragement']}"
                
            # Add reminder setup message
            if goal.reminder_times:
                reminder_text = ", ".join(goal.reminder_times)
                base_response += f" I'll remind you at {reminder_text} each day!"
                
            return base_response
            
        except Exception as e:
            logger.error(f"❌ Error generating goal creation response: {e}")
            return "Great! I'm here to support you on this journey! 🌟"
            
    def generate_progress_summary(self, goals: List[AccountabilityGoal], 
                                streaks: List[ProgressStreak]) -> str:
        """Generate a summary of overall progress"""
        try:
            if not goals:
                return "Ready to set up your first accountability goal? I'm here to help! 🌟"
                
            summary_parts = ["Here's how you're doing with your goals:\n"]
            
            for goal in goals:
                # Find corresponding streak
                streak = next((s for s in streaks if s.goal_id == goal.goal_id), None)
                
                if streak:
                    if streak.current_streak > 0:
                        summary_parts.append(
                            f"🔥 {goal.title}: {streak.current_streak} day streak! "
                            f"({streak.total_successful_days}/{streak.total_days_tracked} total success)"
                        )
                    else:
                        summary_parts.append(
                            f"🎯 {goal.title}: Ready for a fresh start! "
                            f"({streak.total_successful_days}/{streak.total_days_tracked} total success)"
                        )
                else:
                    summary_parts.append(f"🆕 {goal.title}: Just getting started!")
                    
            # Add overall encouragement
            total_streaks = sum(s.current_streak for s in streaks)
            if total_streaks > 10:
                summary_parts.append("\nYou're building amazing momentum! Keep it up! 🚀")
            elif total_streaks > 0:
                summary_parts.append("\nGreat progress! You're building strong habits! 💪")
            else:
                summary_parts.append("\nEvery journey starts with a single step! You've got this! 🌟")
                
            return "\n".join(summary_parts)
            
        except Exception as e:
            logger.error(f"❌ Error generating progress summary: {e}")
            return "You're doing great! Keep up the good work! 🌟"
            
    def generate_motivation_message(self, goal: AccountabilityGoal) -> str:
        """Generate a motivational message based on goal"""
        try:
            motivational_messages = {
                GoalCategory.SOBRIETY: [
                    "Every sober day is a gift to your future self! 💎",
                    "You're choosing clarity, health, and freedom! 🌟",
                    "Your strength in recovery inspires everyone around you! 💪"
                ],
                GoalCategory.MEDITATION: [
                    "Your mind is like a muscle - you're making it stronger! 🧠💪",
                    "Each moment of mindfulness creates more peace in your life! ☮️",
                    "You're building a sanctuary of calm within yourself! 🏛️"
                ],
                GoalCategory.HEALTH_FITNESS: [
                    "Your body is your temple - you're taking great care of it! 🏛️",
                    "Every healthy choice is an investment in your future! 📈",
                    "You're building strength, energy, and vitality! ⚡"
                ],
                GoalCategory.MENTAL_HEALTH: [
                    "Taking care of your mental health is the ultimate self-care! 🧠💚",
                    "You're prioritizing your wellbeing - that's so important! 🌸",
                    "Your mental health journey is brave and inspiring! 🦋"
                ]
            }
            
            category_messages = motivational_messages.get(goal.category, [
                "You're building something amazing! 🌟",
                "Your dedication is inspiring! 💪",
                "Keep going - you're doing great! 🚀"
            ])
            
            return random.choice(category_messages)
            
        except Exception as e:
            logger.error(f"❌ Error generating motivation message: {e}")
            return "You're doing amazing! Keep it up! 🌟"
            
    def _get_streak_message(self, streak_days: int) -> Optional[str]:
        """Get celebration message for streak milestone"""
        # Check for exact milestones
        if streak_days in self.streak_celebrations:
            return self.streak_celebrations[streak_days]
            
        # Check for general milestones
        if streak_days % 30 == 0 and streak_days > 90:
            months = streak_days // 30
            return f"{months} months strong! You're absolutely incredible! 🏆"
        elif streak_days % 7 == 0 and streak_days > 21:
            weeks = streak_days // 7
            return f"{weeks} weeks of consistency! Amazing work! 🎯"
            
        return None
        
    def _generate_metric_responses(self, responses: List[CheckInResponse], 
                                 goal: AccountabilityGoal) -> List[str]:
        """Generate specific responses to individual metric responses"""
        metric_responses = []
        
        try:
            for response in responses:
                if response.response_type.value == "yes_no":
                    if response.yes_no_value:
                        metric_responses.append(f"Great job with {response.metric_name}! ✅")
                    else:
                        metric_responses.append(f"No worries about {response.metric_name} - tomorrow's a new day! 💪")
                        
                elif response.response_type.value == "rating":
                    if response.rating_value and response.rating_value >= 8:
                        metric_responses.append(f"Excellent {response.metric_name} rating! 🌟")
                    elif response.rating_value and response.rating_value >= 6:
                        metric_responses.append(f"Good work on {response.metric_name}! 👍")
                    elif response.rating_value and response.rating_value >= 4:
                        metric_responses.append(f"Thanks for being honest about {response.metric_name}! 💙")
                    else:
                        metric_responses.append(f"Tough day with {response.metric_name} - that's okay! 🤗")
                        
        except Exception as e:
            logger.error(f"❌ Error generating metric responses: {e}")
            
        return metric_responses
        
    def generate_reminder_message(self, goal: AccountabilityGoal, reminder_type: str = "general") -> str:
        """Generate reminder message for a goal"""
        try:
            if reminder_type == "morning":
                templates = [
                    f"Good morning! Just a gentle reminder about your '{goal.title}' goal today! 🌅",
                    f"Rise and shine! Don't forget about '{goal.title}' today! ☀️",
                    f"Morning reminder: You've got this with '{goal.title}' today! 💪"
                ]
            elif reminder_type == "evening":
                templates = [
                    f"Evening check-in time! How did '{goal.title}' go today? 🌙",
                    f"End of day reminder: Let's see how '{goal.title}' went! ⭐",
                    f"Time to reflect on your '{goal.title}' goal today! 🌆"
                ]
            else:
                templates = [
                    f"Friendly reminder about your '{goal.title}' goal! 🔔",
                    f"Don't forget about '{goal.title}' - you've got this! 💪",
                    f"Just checking in on your '{goal.title}' goal! 🌟"
                ]
                
            return random.choice(templates)
            
        except Exception as e:
            logger.error(f"❌ Error generating reminder message: {e}")
            return f"Friendly reminder about your '{goal.title}' goal! 🔔"
            
    def _personalize_response(self, response: str, user_profile: UserProfileData, 
                            agent_record: Optional[AccountabilityAgentRecord] = None) -> str:
        """Personalize response based on user profile and agent learning data"""
        try:
            personalized = response
            
            # Adjust tone based on preferences
            if user_profile.preferences:
                tone = user_profile.preferences.get('tone', 'friendly')
                communication_style = user_profile.preferences.get('communication_style', 'warm')
                
                if tone == 'professional':
                    # Make more formal
                    personalized = personalized.replace('!', '.').replace('You\'ve got this', 'You can achieve this')
                    personalized = personalized.replace('🔥', '⭐').replace('💪', '✅')
                elif tone == 'casual':
                    # Make more casual
                    personalized = personalized.replace('Excellent work', 'Awesome job')
                    personalized = personalized.replace('Well done', 'Nice work')
                    
            # Adapt based on personality traits
            if user_profile.personality_traits:
                if 'introvert' in user_profile.personality_traits:
                    # More gentle approach
                    personalized = personalized.replace('You\'re on fire', 'You\'re doing great')
                    personalized = personalized.replace('!', '.', 1)  # Reduce one exclamation
                    
                if 'optimistic' in user_profile.personality_traits:
                    # Add future-focused language
                    if 'goal' in personalized and 'tomorrow' not in personalized:
                        personalized += ' Tomorrow will be even better!'
                        
            # Add name if available and response is positive
            if user_profile.name and any(word in personalized.lower() for word in ['great', 'awesome', 'excellent', 'fantastic']):
                if user_profile.name not in personalized:
                    personalized = personalized.replace('You', user_profile.name, 1)
                    
            return personalized
            
        except Exception as e:
            logger.error(f"❌ Error personalizing response: {e}")
            return response  # Return original if personalization fails
